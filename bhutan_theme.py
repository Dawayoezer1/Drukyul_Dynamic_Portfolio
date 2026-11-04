import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Lora:wght@400;500&family=Noto+Serif+Tibetan&display=swap');

html, body, [class*="css"], .stApp { font-family: 'Lora', serif; }
.stApp {
  background:
    radial-gradient(circle at 10% 0%, #FFE9A8 0%, transparent 35%),
    radial-gradient(circle at 100% 100%, #F7C873 0%, transparent 30%),
    #FFF8E7;
}

/* Kira-style woven border across the top */
.stApp::before {
  content: ""; position: fixed; top: 0; left: 0; right: 0; height: 10px; z-index: 999;
  background: repeating-linear-gradient(90deg,
    #7B1E1E 0 24px, #F5A800 24px 32px, #1F5E3B 32px 56px, #F5A800 56px 64px,
    #C8102E 64px 88px, #FFF8E7 88px 96px);
}

/* Headings */
h1, h2, h3 { font-family: 'Cinzel', serif !important; color: #7B1E1E !important; letter-spacing: .5px; }
h1 { border-bottom: 3px double #D4A017; padding-bottom: .3rem; }

/* Expander = thangka-style card */
[data-testid="stExpander"] {
  background: #FFFDF5; border: 2px solid #D4A017 !important; border-radius: 10px;
  box-shadow: 0 0 0 4px #FFF8E7, 0 0 0 5px #7B1E1E;
}
[data-testid="stExpander"] summary { color: #7B1E1E; font-weight: 600; }

/* Buttons */
.stButton > button {
  background: linear-gradient(180deg, #F5A800, #E07B00); color: #3B1010;
  border: 2px solid #7B1E1E; border-radius: 8px; font-family: 'Cinzel', serif; font-weight: 700;
}
.stButton > button:hover { background: #7B1E1E; color: #FFD866; border-color: #D4A017; }

/* Selected stock tags: green -> maroon with gold text */
span[data-baseweb="tag"] { background: #7B1E1E !important; color: #FFD866 !important; border-radius: 6px; }
span[data-baseweb="tag"] span[role="presentation"] svg { fill: #FFD866 !important; }

/* Inputs */
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {
  background: #FFFDF5 !important; border: 1.5px solid #D4A017 !important; border-radius: 8px;
}

/* Metrics + sidebar + tabs */
[data-testid="stMetric"] { background: #FFFDF5; border-left: 5px solid #C8102E; padding: .6rem 1rem; border-radius: 8px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #7B1E1E, #4A1010); }
[data-testid="stSidebar"] * { color: #FFE9A8 !important; }
.stTabs [aria-selected="true"] { color: #C8102E !important; border-bottom-color: #F5A800 !important; }
</style>
"""

def apply_bhutan_theme():
    st.markdown(CSS, unsafe_allow_html=True)

def bhutan_banner(title="Drukyul Dynamic Portfolio", subtitle="Land of the Thunder Dragon · Gross National Happiness meets Modern Portfolio Theory"):
    st.markdown(f"""
    <div style="text-align:center;padding:1.2rem;margin:.8rem 0 1.2rem;border:2px solid #D4A017;
                border-radius:12px;background:linear-gradient(135deg,#7B1E1E,#C8102E 55%,#F5A800);">
      <div style="font-family:'Noto Serif Tibetan',serif;font-size:2rem;color:#FFE9A8;">འབྲུག་ཡུལ།</div>
      <div style="font-family:'Cinzel',serif;font-size:1.7rem;color:#FFF8E7;font-weight:700;">🐉 {title}</div>
      <div style="color:#FFE9A8;font-size:.95rem;">{subtitle}</div>
    </div>""", unsafe_allow_html=True)