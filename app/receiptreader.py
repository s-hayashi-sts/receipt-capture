from google.cloud import vision
import re
import cv2
import numpy as np
import copy
from flask import session



#必要な変数：/uploadから受け取ったファイル
class ReceiptReader:
    def __init__(self, file_storage):
        # file_storage は Werkzeug の FileStorage オブジェクト
        self.filename = file_storage.filename
        self.content = file_storage.read()

        #bytes → numpy arr　変換
        nparr = np.frombuffer(self.content, np.uint8)
        self.img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    #Vision APIで画像を読み込む関数
    def file_read(self, img_bytes):
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=img_bytes)

        response = client.document_text_detection(image=image)
        annotation = response.full_text_annotation

        return annotation

        #texts = response.text_annotations
        #text = texts[0].description
        #lines = text.split("\n")
        #item_price_pattern = re.compile(r"(.+?)\s+(\d{2,5})\s*$")
        
    #文字列データの整形
    def reconstruct_lines(self, annotation):
        words = []

        for page in annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        text = "".join([s.text for s in word.symbols])
                        # bounding box の y 座標（上側2点の平均）
                        y = (word.bounding_box.vertices[0].y + word.bounding_box.vertices[1].y) / 2
                        x = word.bounding_box.vertices[0].x
                        words.append((y, x, text))
        
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
                #次の行の最初の単語
                current_line = [(x, text)]
                current_y = y

        # 最後の行
        if current_line:
            current_line.sort(key=lambda w: w[0])
            lines.append(" ".join([t for _, t in current_line]))
        

        #linesから必要な行のみを抜き出す
        new_lines = []
        start_flag = False
        # 判定用の正規表現
        break_pattern = re.compile(r"(合\s*計|小\s*計|お\s*釣\s*り)")

        for line in lines:
            if not start_flag:
                #日付・ハイフン込み電話番号・番地を除外（数字の連続が3回以上を除外）
                if len(re.findall(r"\d+", line)) >= 3:
                    continue
                
                #4回以上の数字の連続を含む場合を除外（間にカンマが入らないため、金額でないと判断→筐体番号、登録番号など）
                if re.search(r"\d{4,}", line):
                    continue
                
                #数字を含まない行を除外(購買情報と関係の無いテキスト)
                if not re.search(r"\d", line):
                    continue
            else:
                start_flag = True
            
            #合計or小計orお釣りまで来たら処理を抜ける
            #判定処理
            if break_pattern.search(line):
                start_flag = False
                break


            #品目・価格を含む文字列を新しい配列に格納
            new_lines.append(line)

        #linesを価格と品目に分割し、辞書化
        items = []
        
        pattern = re.compile(r"^(.*?)\s*￥?\s*(\d+)\D*$")

        for line in new_lines:
            m = pattern.match(line)
            
            if m:
                #品目を抽出
                raw_name = m.group(1)
                #品目の文字列から空白を除去
                name = re.sub(r"\s+", " ", raw_name).strip()
                #価格を抽出
                price = int(m.group(2))
                items.append({"name":name, 
                              "price":price, 
                              "tax_mode":"default"})
        
        #割引の扱い
        #割引・割＊引を含む場合、「割引」カテゴリとして登録する
        new_items = []
        # 割引判定用の正規表現
        discount_pattern = re.compile(r"(割\s*引|値\s*引)")
        # 割引を含む行を new_items に追加しないためのflag
        skip_flag = False
        for i, item in enumerate(items):
            if i == 0:
                continue
            #1つ前の要素が割引の場合は処理をスキップ
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
                new_items.append({"name":items[i - 1]["name"], 
                              "price":modified_price, 
                              "tax_mode":"default"})
                skip_flag = True
            else:
                # 通常品目は new_items に追加
                new_items.append(items[i - 1])

            #リストの最後の要素に対する処理（割引でない場合）
            if i == (len(items)-1):
                new_items.append(item)

        #セッションに割引、税額、itemsを登録
        session["discount"] = {"name": "割引", "price": 0}
        session["tax"] = [{"name": "外税 8%", "price":0}, 
                          {"name":"外税 10%", "price":0}]
        session["receipt_items"] = new_items

        #合計金額の計算
        total = 0
        for item in new_items:
            price = item["price"]

            total += price
        
        total_amount = {"name": "合計", "price": total}
        # セッションに合計を登録
        session["total_amount"] = total_amount

        #セッションの初期状態を保存
        session["base_receipt_items"] = copy.deepcopy(new_items)
        session["base_discount"] = {"name": "割引", "price": 0}
        session["base_tax"] = [{"name": "外税 8%", "price":0}, 
                          {"name":"外税 10%", "price":0}]
        session["base_total_amount"] = copy.deepcopy(total_amount)
        
        
    #OCR前処理
    def deskew(self):
        #グレースケール
        gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        #二値化
        th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        coords = cv2.findNonZero(th)
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        (h, w) = self.img.shape[:2]
        M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
        rotated = cv2.warpAffine(self.img, M, (w, h))

        print("angle:", angle)

        #numpy arr → bytes変換
        _, encoded_img = cv2.imencode(".png", rotated)
        img_bytes = encoded_img.tobytes()

        return img_bytes
        

        #この後の流れ
        '''画像読み込み→必要情報をDBに登録'''
        #認証情報（サービスアカウントキー）を環境変数で設定する必要がある
        #labelでレシート判定→文字の検出？




