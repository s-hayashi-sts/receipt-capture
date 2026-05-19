from google.cloud import vision



#必要な変数：/uploadから受け取ったファイル
class ReceiptReader:
    def __init__(self, file_storage):
        # file_storage は Werkzeug の FileStorage オブジェクト
        self.filename = file_storage.filename
        self.content = file_storage.read()
    
    def file_read(self):
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=self.content)
        response_label = client.label_detection(image=image)
        labels = response_label.label_annotations

        print('Labels:')
        for label in labels:
            print(label.description, ':', label.score)
        
        response = client.document_text_detection(image=image)
        texts = response.text_annotations
        print('Text:')
        print(texts[0].description)

        #この後の流れ
        '''画像読み込み→必要情報をDBに登録'''
        #認証情報（サービスアカウントキー）を環境変数で設定する必要がある
        #labelでレシート判定→文字の検出？




