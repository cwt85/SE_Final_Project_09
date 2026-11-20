# common/templating.py
# 共用的 Jinja2 模板設定。
#
# 每個模組把模板放在「自己的資料夾/templates/模組名稱/」底下，例如：
#   space_query/templates/space_query/index.html
# 使用時寫 render(request, "space_query/index.html", rooms=rooms)
# 多一層「模組名稱」資料夾，是為了避免不同模組都有 index.html 時互相蓋掉。
from fastapi import Request

from fastapi.templating import Jinja2Templates

from common.auth import ROLE_LABELS, current_user
from common.config import BASE_DIR, MODE_LABELS
from common.db import available_modes, get_mode

# 所有模組的模板資料夾；新增模組時要加在這裡
TEMPLATE_DIRS = [
	BASE_DIR / "common" / "templates",
	BASE_DIR / "space_query" / "templates",
	BASE_DIR / "space_booking" / "templates",
	BASE_DIR / "course_schedule" / "templates",
]

templates = Jinja2Templates(directory=TEMPLATE_DIRS)

# 讓所有模板都能直接用這些對照表，例如 {{ ROLE_LABELS[user.role] }}
templates.env.globals["ROLE_LABELS"] = ROLE_LABELS
templates.env.globals["MODE_LABELS"] = MODE_LABELS


def render(request: Request, name: str, status_code: int = 200, **context):
	"""
	產生 HTML 回應。會自動放進這些模板變數：
	  user       目前登入的使用者（沒登入是 None），導覽列用來決定顯示「登入」或「登出」
	  db_mode    目前的資料庫模式（"local" / "cloud"），導覽列會顯示
	  db_modes   有設定的模式清單，登入頁的切換開關用
	"""
	context.setdefault("user", current_user(request))
	context.setdefault("db_mode", get_mode(request))
	context.setdefault("db_modes", available_modes(request))
	return templates.TemplateResponse(request, name, context, status_code=status_code)
