import copy
import re
from datetime import datetime

import cv2
import numpy as np
from flask import session
from google.cloud import vision


class ReceiptValidationError(Exception):
    # レシートの画像やOCR結果が不正な場合に発生させる例外
    pass


# 必要な変数：/uploadから受け取ったファイル
class ReceiptReader:
    def __init__(self, file_storage):
        # file_storage は Werkzeug の FileStorage オブジェクト
        self.filename = file_storage.filename
        self.content = file_storage.read()

        # bytes → numpy arr　変換
        nparr = np.frombuffer(self.content, np.uint8)
        self.img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # ガンマ補正 後で消す
    def _adjust_gamma(self, image, gamma=1.5):
        inv = 1.0 / gamma
        table = np.array([(i / 255.0) ** inv * 255 for i in range(256)]).astype("uint8")
        return cv2.LUT(image, table)

    # OCR前処理 ハフ変換で傾きを補正
    def deskew(self):
        # グレースケール
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        # 二値化
        th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        coords = cv2.findNonZero(th)
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        (h, w) = self.img.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        rotated = cv2.warpAffine(self.img, M, (w, h))

        print("angle:", angle)  # デバッグ用

        # ガンマ補正（暗いレシートを明るく補正）
        gamma = 1.5
        inv = 1.0 / gamma
        table = np.array([(i / 255.0) ** inv * 255 for i in range(256)]).astype("uint8")
        brightened = cv2.LUT(rotated, table)

        # 3. 適応的ヒストグラム平坦化 (CLAHE) の追加（文字の輪郭をくっきりさせる）
        # CLAHEはグレースケールに適用するため、一度変換して適用後、再度カラー（または輝度調整）に反映、
        # もしくはそのまま処理。ここでは最も効果の高い、輝度(Y)チャンネルへの適用を行います。
        ycrcb = cv2.cvtColor(brightened, cv2.COLOR_BGR2YCrCb)
        y, cr, cb = cv2.split(ycrcb)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        y_enhanced = clahe.apply(y)
        merged = cv2.merge([y_enhanced, cr, cb])
        final_img = cv2.cvtColor(merged, cv2.COLOR_YCrCb2BGR)

        # numpy arr → bytes変換
        _, encoded_img = cv2.imencode(".png", final_img)
        img_bytes = encoded_img.tobytes()

        return img_bytes

    # Vision APIで画像を読み込む関数
    def file_read(self, img_bytes):
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=img_bytes)

        response = client.document_text_detection(image=image)
        annotation = response.full_text_annotation

        return annotation

    # 文字の Confidence Score（信頼度）のチェック
    def check_confidence(
        self, annotation, confidence_threshold=0.8, error_ratio_threshold=0.15
    ):
        total_symbols = 0
        low_confidence_symbols = 0

        if not annotation or not annotation.pages:
            raise ReceiptValidationError(
                "文字を検出できませんでした。画像を明るく鮮明に撮影し直してください。"
            )

        for page in annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        for symbol in word.symbols:
                            total_symbols += 1
                            # 信頼度が設定値（0.8）未満の場合にカウント
                            if symbol.confidence < confidence_threshold:
                                low_confidence_symbols += 1

        if total_symbols == 0:
            raise ReceiptValidationError("認識可能な文字が含まれていません。")

        # 低信頼度の割合を算出
        low_confidence_ratio = low_confidence_symbols / total_symbols
        if low_confidence_ratio >= error_ratio_threshold:
            raise ReceiptValidationError(
                f"画像の文字を正確に読み取れませんでした（不鮮明度: {low_confidence_ratio:.1%}）。"
                "レシート全体を、ピントを合わせてまっすぐ撮影してください。"
            )

    # 日時を正規表現を用いて抽出する関数
    def extract_to_datetime(self, text):
        # 正規表現パターン（例: "2026/07/02 22:01" や "26年07月02日 22時01" など）
        date_pattern = re.compile(
            r"\b(?:\d{4}|\d{2})[-/年]\d{1,2}[-/月]\d{1,2}.+?\d{1,2}[-:：時\s]\d{1,2}"
        )

        # 検索実行
        match = date_pattern.search(text)

        if not match:
            return None  # 日時が見つからなかった場合

        # マッチした文字列
        matched_str = match.group(0)

        # 文字列から数字だけをすべて取り出してリスト化
        # 例: ['2026', '07', '02', '22', '01'] や ['26', '7', '2', '22', '01']
        numbers = re.findall(r"\d+", matched_str)

        # 各要素を整数（int）に変換
        year = int(numbers[0])
        month = int(numbers[1])
        day = int(numbers[2])
        hour = int(numbers[3])
        minute = int(numbers[4])

        # 西暦が下2桁（例: 26年）で取得されてしまった場合の補正（2000年代を想定）
        if year < 100:
            year += 2000

        # 5. datetimeオブジェクトを生成して返す
        try:
            dt = datetime(year, month, day, hour, minute).strftime("%Y-%m-%d %H:%M")
            return dt
        except ValueError as e:
            # 2月31日のような不正な日付だった場合のセーフティ
            print(f"無効な日付です: {e}")
            return None

    # 文字列データの整形
    def reconstruct_lines(self, annotation):
        words = []

        for page in annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        text = "".join([s.text for s in word.symbols])
                        # bounding box の y 座標（上側2点の平均）
                        y = (
                            word.bounding_box.vertices[0].y
                            + word.bounding_box.vertices[1].y
                        ) / 2
                        x = word.bounding_box.vertices[0].x
                        words.append((y, x, text))

        # wordsの長さが0ならエラー
        if len(words) == 0:
            raise ReceiptValidationError(
                "画像から情報を読み取れませんでした。レシートの文字がはっきりと映るように撮影してください"
            )

        # y 座標でソート（行順）
        words.sort(key=lambda w: (round(w[0] / 10), w[1]))

        lines = []
        current_y = None
        current_line = []

        for y, x, text in words:
            if current_y is None:
                current_y = y

            # y が近ければ同じ行 #閾値は文字のサイズによって変えられると尚いい
            if abs(y - current_y) < 15:
                current_line.append((x, text))
            else:
                # 行を確定
                current_line.sort(key=lambda w: w[0])
                lines.append(" ".join([t for _, t in current_line]))
                # 次の行の最初の単語
                current_line = [(x, text)]
                current_y = y

        # 最後の行
        if current_line:
            current_line.sort(key=lambda w: w[0])
            lines.append(" ".join([t for _, t in current_line]))

        # linesから必要な行のみを抜き出す
        new_lines = []
        # 商品の購入日（デフォルトは現在の日時）
        register_datetime = {
            "name": "登録日時",
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        # 日付判定済みかをチェックするフラグ
        datetime_flag = False
        # 読み取り終了判定用の正規表現
        break_pattern = re.compile(r"(合\s*計|小\s*計|お\s*釣\s*り)")
        # break_patternにヒットしたかどうかのフラグ
        has_break_pattern = False
        for line in lines:
            # 買い物をした日時を抽出
            if not datetime_flag:
                extract = self.extract_to_datetime(line)
                if extract is not None:
                    register_datetime = {"name": "登録日時", "datetime": extract}
                    datetime_flag = True

            # ハイフン込み電話番号・番地を除外（数字の連続が3回以上を除外）
            if len(re.findall(r"\d+", line)) >= 3:
                continue

            # 4回以上の数字の連続を含む場合を除外（間にカンマが入らないため、金額でないと判断→筐体番号、登録番号など）
            if re.search(r"\d{4,}", line):
                continue

            # 数字を含まない行を除外(購買情報と関係の無いテキスト)
            if not re.search(r"\d", line):
                continue

            # 合計or小計orお釣りまで来たら処理を抜ける
            # 判定処理
            if break_pattern.search(line):
                has_break_pattern = True  # ヒットしたことを記録
                break

            # 品目・価格を含む可能性のある文字列を新しい配列に格納
            new_lines.append(line)

        # 合計・小計・お釣りのいずれも見つからずに終了した場合エラー
        if not has_break_pattern:
            raise ReceiptValidationError(
                "レシートの「合計金額」や「小計」の行が見つかりませんでした。"
            )

        # new_linesの長さが0ならエラー
        if len(new_lines) == 0:
            raise ReceiptValidationError(
                "レシートから購買データが見つかりませんでした。"
            )

        # linesを価格と品目に分割し、辞書化
        items = []
        # 何の正規表現？
        pattern = re.compile(r"^(.*?)\s*￥?\s*(\d+)\D*$")

        for line in new_lines:
            m = pattern.match(line)

            if m:
                # 品目を抽出
                raw_name = m.group(1)
                # 品目の文字列から空白を除去
                name = re.sub(r"\s+", " ", raw_name).strip()
                # 価格を抽出
                price = int(m.group(2))
                items.append({"name": name, "price": price, "tax_mode": "default"})

        # 割引の扱い
        # 割引・割＊引を含む場合、「割引」カテゴリとして登録する
        new_items = []
        # 割引判定用の正規表現
        discount_pattern = re.compile(r"(割\s*引|値\s*引)")
        # 割引を含む行を new_items に追加しないためのflag
        skip_flag = False
        for i, item in enumerate(items):
            if i == 0:
                continue
            # 1つ前の要素が割引の場合は処理をスキップ
            if skip_flag:
                skip_flag = False
                continue

            # 割引行かどうかを判定
            if discount_pattern.search(item["name"]):
                # 1つ前の要素のprice
                prev_price = items[i - 1]["price"]
                # 現在の要素のprice
                current_price = item["price"]
                # 割引金額を1つ前の要素の金額から差し引く
                modified_price = prev_price - current_price
                # 1つ前の要素をnew_itemsへ追加
                new_items.append(
                    {
                        "name": items[i - 1]["name"],
                        "price": modified_price,
                        "tax_mode": "default",
                    }
                )
                skip_flag = True
            else:
                # 通常品目は new_items に追加
                new_items.append(items[i - 1])

            # リストの最後の要素に対する処理（割引でない場合）
            if i == (len(items) - 1):
                new_items.append(item)

        # セッションに購入日時、割引、税額、items、税率計算方法を登録
        session["register_datetime"] = register_datetime
        session["discount"] = {"name": "割引", "price": 0}
        session["tax"] = [
            {"name": "外税 8%", "price": 0},
            {"name": "外税 10%", "price": 0},
        ]
        session["receipt_items"] = new_items
        session["tax_calc_mode"] = "all"

        # 合計金額の計算
        total = 0
        for item in new_items:
            price = item["price"]

            total += price

        total_amount = {"name": "合計", "price": total}
        # セッションに合計を登録
        session["total_amount"] = total_amount

        # セッションの初期状態を保存
        session["base_register_datetime"] = copy.deepcopy(register_datetime)
        session["base_receipt_items"] = copy.deepcopy(new_items)
        session["base_discount"] = {"name": "割引", "price": 0}
        session["base_tax"] = [
            {"name": "外税 8%", "price": 0},
            {"name": "外税 10%", "price": 0},
        ]
        session["base_total_amount"] = copy.deepcopy(total_amount)
