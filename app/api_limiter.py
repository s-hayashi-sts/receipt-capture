import time
from datetime import datetime

from sqlalchemy.exc import OperationalError

from apps.app.main import db
from apps.app.models import ApiUsage

# Google Cloud Vision APIの無料枠(月間)。
MONTHLY_LIMIT = 1000

"""
当月のVISION API呼び出し回数を確認し、上限未満であればカウントを1増やしてTrueを返す。
上限に達していればFalseを返す
"""


def check_api_usage(max_retries=3, delay=0.2):
    year_month = datetime.now().strftime("%Y-%m")
    """
    SQLite等で行ロック（with_for_update）未対応またはDBロック競合が発生した場合、
    OperationalErrorをキャッチしてリトライを行う
    """
    for attempt in range(max_retries):
        try:
            # トランザクション内で参照・更新を行う
            # ※SQLiteでは for_update() は無視されますが、他DB移行時にも機能します
            usage = (
                ApiUsage.query.filter_by(year_month=year_month)
                .with_for_update()
                .first()
            )

            if not usage:
                usage = ApiUsage(year_month=year_month, count=0)
                db.session.add(usage)
                db.session.flush()

            # 利用制限上限チェック
            if usage.count >= MONTHLY_LIMIT:
                return False, "今月のAPI利用上限に達しました。"

            # カウントアップ
            usage.count += 1
            db.session.commit()
            return True, None

        except OperationalError as e:
            db.session.rollback()
            # SQLiteのロックエラー（database is locked）の場合はリトライ
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt < max_retries - 1:
                    time.sleep(delay)  # 少し待機してから再試行
                    continue

            # リトライ上限超過、またはその他のOperationalError
            return (
                False,
                "通信が混雑しています。時間を置いて再度お試しください。",
            )

        except Exception as e:
            db.session.rollback()
            # その他の予期せぬエラーハンドリング
            return False, f"エラーが発生しました: {str(e)}"

    return False, "通信が混雑しています。時間をおいて再度お試しください。"
