import copy
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import cv2
import gc


# import easyocr
import numpy as np
from flask import session
from google.cloud import vision
from onnxocr.onnx_paddleocr import ONNXPaddleOcr
from PIL import Image, ImageEnhance


class ReceiptValidationError(Exception):
    # レシートの画像やOCR結果が不正な場合に発生させる例外
    pass


# 必要な変数：/uploadから受け取ったファイル
class ReceiptReader:
    def __init__(self, file_storage):
        # file_storage は Werkzeug の FileStorage オブジェクト
        self.content = file_storage.read()

        # bytes → numpy arr　変換
        nparr = np.frombuffer(self.content, np.uint8)
        self.img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # 前処理1 リサイズ
    def resize_image(self, raw_img, max_side=2000):
        h, w = raw_img.shape[:2]
        longest_side = max(h, w)
        if longest_side > max_side:
            scale = max_side / longest_side
            resized_img = cv2.resize(
                raw_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
            )
            h, w = resized_img.shape[:2]
            print("リサイズ確認：", "h:", h, "w:", w)

            return resized_img
        else:
            return raw_img

    # 前処理2 コントラスト強化
    def ajdust_image(self, raw_img):
        # OpenCV(BGR, NumPy配列) → Pillow(RGB, Imageオブジェクト)へ変換
        img_rgb = cv2.cvtColor(raw_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        # 前処理 コントラスト
        enhancer = ImageEnhance.Contrast(pil_img)
        modified_pil_img = enhancer.enhance(4)
        # pil → nmpy変換
        modified_img = cv2.cvtColor(np.array(modified_pil_img), cv2.COLOR_RGB2BGR)

        return modified_img

    # OCR前処理
    def deskew_and_adjustment(self):
        # コントラスト強化
        modified_img = self.ajdust_image(raw_img=self.img)
        # リサイズ
        resized_img = self.resize_image(raw_img=modified_img)

        """文字検出→検出範囲に対して最小外接矩形を描画し、画像の傾きを補正する"""
        ocr = ONNXPaddleOcr(use_gpu=False, lang="japan", drop_score=0.4)
        result = ocr.ocr(resized_img, rec=False)

        # 処理完了後、メモリを明示的に解放する
        del ocr
        gc.collect()

        h, w = resized_img.shape[:2]

        # 黒背景のマスク画像を準備 (全要素が 0 = 黒)
        mask = np.zeros((h, w), dtype=np.uint8)

        for data in result:
            for box in data:
                # 検出された領域を白（255）で塗りつぶす
                pts = np.array(box, dtype=np.int32)
                cv2.fillPoly(mask, [pts], 255)

        # マスク画像から白ピクセル（文字領域）の座標を取得
        coords = cv2.findNonZero(mask)

        # 文字ピクセルが存在する場合のみ傾き計算
        if coords is not None:
            # 文字ピクセルを囲む最小の長方形を求める
            rect = cv2.minAreaRect(coords)

            # 最小外接矩形の4頂点
            box = cv2.boxPoints(rect)
            box = np.int32(box)

            # 4辺の長さを求める
            edges = []

            for i in range(4):
                p1 = box[i]
                p2 = box[(i + 1) % 4]

                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]

                length = math.hypot(dx, dy)

                edges.append((length, dx, dy))

            # 最長辺を取得
            _, dx, dy = max(edges, key=lambda e: e[0])

            # 長辺の角度
            angle = np.degrees(np.arctan2(dy, dx))

            print("angle:", angle)  # デバッグ用

            # 長辺を垂直に揃える
            rotate_angle = 90 - angle

            # 回転量を -90～90 に収める
            if rotate_angle > 90:
                rotate_angle -= 180
            elif rotate_angle < -90:
                rotate_angle += 180

            angle = rotate_angle
            angle = -angle

        # 画像を回転
        (h, w) = resized_img.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)

        # 回転後の余白を白で埋める
        rotated = cv2.warpAffine(
            resized_img,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )

        # numpy arr → bytes変換
        _, encoded_img = cv2.imencode(".png", rotated)
        img_bytes = encoded_img.tobytes()

        return img_bytes

    # Vision APIで画像を読み込む関数
    def file_read(self, img_bytes):
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=img_bytes)

        response = client.document_text_detection(image=image)

        return response.full_text_annotation

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
                "文字を検出できませんでした。画像を明るく鮮明に撮影し直してください。"
            )

    # 日時を正規表現を用いて抽出する関数
    def extract_to_datetime(self, text):
        # 正規表現パターン（例: "2026/07/02 22:01" や "26年07月02日 22時01" など）
        date_pattern = re.compile(
            r"(\d{2,4})[-/年](\d{1,2})[-/月](\d{1,2})日?.*?(\d{1,2})[:：時](\d{1,2})"
        )

        # 検索実行
        match = date_pattern.search(text)

        if not match:
            return None  # 日時が見つからなかった場合

        # マッチした文字列
        year, month, day, hour, minute = map(int, match.groups())
        print("マッチした文字列", year, month, day, hour, minute)

        # 西暦が下2桁（例: 26年）で取得されてしまった場合の補正（2000年代を想定）
        if year < 100:
            year += 2000

        # datetimeオブジェクトを生成して返す
        try:
            dt = datetime(year, month, day, hour, minute).strftime("%Y-%m-%d %H:%M")
            return dt
        except ValueError as e:
            # 2月31日のような不正な日付だった場合のセーフティ
            print(f"無効な日付です: {e}")
            return None

    # 文字列データの整形
    def reconstruct_lines(self, annotation):
        """紙面の歪み対策 単語の上辺のy座標から同じ行かを判別"""
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
                "文字を検出できませんでした。画像を明るく鮮明に撮影し直してください。"
            )

        # y 座標でソート（行順）
        words.sort(key=lambda w: (round(w[0] / 10), w[1]))

        lines = []
        current_y = None  # 行判定の基準となる値
        current_line = []  # 1行分の文字列

        # 行の作成
        for y, x, text in words:
            if current_y is None:
                current_y = y

            # y が近ければ同じ行 閾値は文字のサイズによって変えられるといい
            if abs(y - current_y) < 15:
                current_line.append((x, text))
            else:
                # y が離れている場合、1つ前までの要素を1行として確定
                current_line.sort(key=lambda w: w[0])
                lines.append(" ".join([t for _, t in current_line]))
                # 次の行の最初の単語
                current_line = [(x, text)]
                current_y = y

        # 最後の行を確定（上記のループ内で確定されないため）
        if current_line:
            current_line.sort(key=lambda w: w[0])
            lines.append(" ".join([t for _, t in current_line]))

        # linesから必要な行のみを抜き出す
        new_lines = []
        # 商品の購入日（デフォルトは現在の日時）
        register_datetime = {
            "name": "登録日時",
            "datetime": datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M"),
        }
        # 日付判定済みかをチェックするフラグ
        datetime_flag = False
        # 読み取り終了判定用の正規表現
        break_pattern = re.compile(r"(合\s*計|小\s*計|お\s*釣\s*り|金\s*額)")
        for line in lines:
            # 買い物をした日時を抽出
            if not datetime_flag:
                extract = self.extract_to_datetime(line)
                if extract is not None:
                    register_datetime = {"name": "登録日時", "datetime": extract}
                    datetime_flag = True

            # ハイフン込み電話番号・番地を除外（数字の連続が3グループ以上を除外）
            if len(re.findall(r"\d+", line)) >= 3:
                continue

            # 4回以上の数字の連続を含む場合を除外（間にカンマが入らないため、金額でないと判断→筐体番号、登録番号など）
            if re.search(r"\d{4,}", line):
                continue

            # 数字を含まない行を除外(購買情報と関係の無いテキスト)
            if not re.search(r"\d", line):
                continue

            # 合計or小計orお釣りor金額まで来たら処理を抜ける
            # 判定処理
            if break_pattern.search(line):
                break

            # 品目・価格を含む可能性のある文字列を新しい配列に格納
            new_lines.append(line)

        # new_linesの長さが0ならエラー
        if len(new_lines) == 0:
            raise ReceiptValidationError(
                "レシートから購買データが見つかりませんでした。"
            )

        # linesを価格と品目に分割し、辞書化
        items = []
        # 品目と金額を分離する正規表現
        pattern = re.compile(r"^(.*?)\s*￥?\s*(\d+)\D*$")

        for line in new_lines:
            m = pattern.match(line)

            if m:
                # 品目を抽出
                raw_name = m.group(1)
                # 品目の文字列から空白を除去
                name = re.sub(r"\s+", "", raw_name).strip()
                # 価格を抽出
                price = int(m.group(2))
                items.append({"name": name, "price": price, "tax_mode": "default"})

        # itemsの長さが0ならエラー
        if len(items) == 0:
            raise ReceiptValidationError(
                "レシートから購買データが見つかりませんでした。"
            )

        # 割引の扱い
        # 割引を含む場合、「割引」カテゴリとして登録する
        new_items = []
        # 割引判定用の正規表現
        discount_pattern = re.compile(r"(割\s*引|値\s*引)")
        # 割引を含む行を new_items に追加しないためのflag
        skip_flag = False
        for i, item in enumerate(items):
            if skip_flag:
                skip_flag = False
                continue

            # 次の要素が割引行かどうかを判定
            if i + 1 < len(items) and discount_pattern.search(items[i + 1]["name"]):
                discount_price = items[i + 1]["price"]
                modified_price = item["price"] - discount_price
                # 1つ前の要素をnew_itemsへ追加
                new_items.append(
                    {
                        "name": item["name"],
                        "price": modified_price,
                        "tax_mode": "default",
                    }
                )
                skip_flag = True  # 次の要素が割引の場合はスキップ
            else:
                # 通常品目は new_items に追加
                new_items.append(item)

        # セッションに購入日時、割引、税額、new_items、税率計算方法を登録
        session["register_datetime"] = register_datetime
        session["discount"] = {
            "name": "割引",
            "price": 0,
        }  # この割引は入力フォームで合計金額を調整するためのもの
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
