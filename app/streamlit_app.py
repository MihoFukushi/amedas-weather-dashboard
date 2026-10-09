"""AMeDAS 観測値の集計結果(DuckDB の marts スキーマ)を表示するダッシュボード。

    streamlit run app/streamlit_app.py

ページは app/views/ 以下に 1 ファイルずつ置き、ここで st.navigation に登録する。
"""

import sys
from pathlib import Path

import streamlit as st

# views/ 配下のページから `import common` できるようにする
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

st.set_page_config(page_title="AMeDAS 気象ダッシュボード", layout="wide")

pages = [
    st.Page("views/timelapse.py", title="コマ送りマップ", icon=":material/play_circle:", default=True),
    st.Page("views/wind.py", title="風の地図と風配図", icon=":material/air:"),
    st.Page("views/profile.py", title="気温の断面図", icon=":material/landscape:"),
]

st.navigation(pages).run()
