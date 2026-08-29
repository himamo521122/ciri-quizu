# -*- coding: utf-8 -*-
"""
中学受験 社会科（地理）4択クイズアプリ
Streamlit で動作します。

■ 動かし方
    pip install -r requirements.txt
    streamlit run app.py

■ 問題の追加方法
    下の QUESTIONS リストに辞書を1つ追加するだけで問題を増やせます。
    (最終的に50問まで増やせる想定です)

    {
        "question": "問題文",
        "correct": "正解の答え",
        "wrong": ["間違いの答え1", "間違いの答え2", "間違いの答え3", ...],
        # wrong は3つ以上あればOK。出題のたびにこの中からランダムで3つ選ばれ、
        # 正解1つと合わせて4択になります。
        "explanations": {},
        # ↑将来、選択肢ごとの解説文を入れたくなったら
        #   "選択肢のテキスト": "解説文",
        # という形で追加してください（今のバージョンでは表示していません）。
    },
"""

import base64
import io
import math
import random
import struct
import time
import wave

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# グラフの日本語（「正解」「不正解」）が文字化けしないよう、
# パソコンに入っている日本語フォントを順番に探して使う設定。
# 追加インストール不要（Windows/Macに標準で入っているフォント名を並べています）。
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Yu Gothic",
    "Meiryo",
    "MS Gothic",
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "Noto Sans CJK JP",
    "IPAexGothic",
    "sans-serif",
]
plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 制限時間（秒）
# ============================================================
TIME_LIMIT_SECONDS = 3 * 60  # 3分


def format_mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


# ============================================================
# 効果音（ding.wav / buzzer.wav）を音声ファイルを使わずPythonで自動生成
# 追加ライブラリのインストールは不要（標準ライブラリのみで作成）
# ============================================================
SAMPLE_RATE = 44100


def _wave_value(shape: str, freq: float, t: float) -> float:
    if freq <= 0:
        return 0.0
    phase = (freq * t) % 1.0
    if shape == "square":
        return 1.0 if phase < 0.5 else -1.0
    return math.sin(2 * math.pi * freq * t)  # "sine"


def _synthesize(segments, sample_rate: int = SAMPLE_RATE) -> bytes:
    """segments: [(shape, freq_hz, duration_sec, volume), ...] を順番に鳴らして
    16bit PCM（モノラル）のバイト列にする。freq=0 は無音（間）として扱う。
    音の頭とお尻を少しフェードさせ、プツッというノイズが出ないようにしている。
    """
    pcm = bytearray()
    fade = 0.015  # 秒
    for shape, freq, duration, volume in segments:
        n = int(sample_rate * duration)
        fade_n = max(1, int(sample_rate * fade))
        for i in range(n):
            t = i / sample_rate
            envelope = 1.0
            if i < fade_n:
                envelope = i / fade_n
            elif i > n - fade_n:
                envelope = max(0.0, (n - i) / fade_n)
            sample = volume * envelope * _wave_value(shape, freq, t)
            pcm += struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
    return bytes(pcm)


def _pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


@st.cache_data
def generate_ding_sound() -> bytes:
    """正解したときの、明るい2音の電子音（ピンポン）。"""
    segments = [
        ("sine", 1046.5, 0.12, 0.5),  # ド（高め）
        ("sine", 1568.0, 0.22, 0.5),  # ソ（さらに高め）
    ]
    return _pcm_to_wav_bytes(_synthesize(segments))


@st.cache_data
def generate_buzzer_sound() -> bytes:
    """不正解のときの、低いブザー音（ブッブッ、と2回鳴る）。"""
    segments = [
        ("square", 150.0, 0.18, 0.35),
        ("square", 0.0, 0.05, 0.0),  # 一瞬の無音
        ("square", 150.0, 0.18, 0.35),
    ]
    return _pcm_to_wav_bytes(_synthesize(segments))


def play_sound_effect(wav_bytes: bytes) -> None:
    """再生ボタンなどを画面に出さず、こっそり自動再生する。"""
    b64 = base64.b64encode(wav_bytes).decode()
    components.html(
        f"""
        <audio autoplay="true" style="display:none">
            <source src="data:audio/wav;base64,{b64}" type="audio/wav">
        </audio>
        """,
        height=0,
        width=0,
    )


# ============================================================
# 問題データ（ここに追加していけば50問まで増やせます）
# ============================================================
QUESTIONS = [
    {
        "question": "イタイイタイ病は何県で発生しましたか。",
        "correct": "富山県",
        "wrong": ["岐阜県", "三重県", "和歌山県", "新潟県"],
        "explanations": {},
    },
    {
        "question": "三重県で発生した公害病（工業病）は何ですか。",
        "correct": "四日市ぜんそく",
        "wrong": ["五日市ぜんそく", "イタイイタイ病", "水俣病", "クサイクサイ病"],
        "explanations": {},
    },
    {
        "question": "新潟水俣病（水俣病）を発生させた原因は何ですか。",
        "correct": "メチル水銀（有機水銀）",
        "wrong": ["レアメタル", "硫黄酸化物", "カドミウム", "メタル水銀"],
        "explanations": {},
    },
    {
        "question": "九州地方から太平洋沿いを流れてくる暖流は何ですか。",
        "correct": "黒潮",
        "wrong": [
            "子潮海流",
            "白潮海流",
            "親潮",
            "リマン海流",
            "対馬海流",
            "マリン海流",
            "千島海流",
        ],
        "explanations": {},
    },
    {
        "question": "第二次世界大戦ごろまでは全国で最大の生産額を上げていた工業地帯・工業地域は何ですか。",
        "correct": "阪神工業地帯",
        "wrong": ["京葉工業地域", "北九州工業地帯（北九州工業地域）", "中京工業地帯", "東海工業地域"],
        "explanations": {},
    },
    {
        "question": "自然の力で電気を作り、環境にやさしい発電方法をまとめて何と言いますか。",
        "correct": "再生可能エネルギー",
        "wrong": [
            "火力発電",
            "原子力発電",
            "自然発電",
            "水力発電",
            "環境発電",
            "風力発電",
            "波力発電",
        ],
        "explanations": {},
    },
    {
        "question": "金属工業、機械工業、化学工業を合わせた工業を何といいますか。",
        "correct": "重化学工業",
        "wrong": ["重工業", "機械工業", "金属きかい化学工業", "自動車工業", "電子工業"],
        "explanations": {},
    },
    {
        "question": "伝統工芸品、漆器の「津軽塗（つがるぬり）」があるのは何県ですか。",
        "correct": "青森県",
        "wrong": ["石川県", "福島県", "宮城県", "岩手県", "茨城県"],
        "explanations": {},
    },
    {
        "question": "伝統工芸品、焼き物の「備前焼（びぜんやき）」があるのは何県ですか。",
        "correct": "岡山県",
        "wrong": ["石川県", "佐賀県", "京都府", "岐阜県", "愛知県"],
        "explanations": {},
    },
    {
        "question": "伝統工芸品、織物の「小千谷ちぢみ（おぢやちぢみ）」があるのは何県ですか。",
        "correct": "新潟県",
        "wrong": ["京都府", "石川県", "福岡県", "富山県", "愛知県"],
        "explanations": {},
    },
    {
        "question": "日本の「米ぐら」と呼ばれる、稲作がさかんな地域はどこですか。",
        "correct": "東北・北陸地方",
        "wrong": ["北海道地方", "関東地方", "九州地方", "近畿地方", "中国・四国地方"],
        "explanations": {},
    },
]

QUIZ_TITLE = "中学受験 社会科（地理）4択クイズ"


# ============================================================
# クイズ生成ロジック
# ============================================================
def generate_quiz(num_questions: int):
    """出題する問題を作る。問題の順番も、各問題の4択の中身・並びもランダム。"""
    pool = random.sample(QUESTIONS, k=min(num_questions, len(QUESTIONS)))
    quiz = []
    for q in pool:
        wrong_choices = random.sample(q["wrong"], k=min(3, len(q["wrong"])))
        choices = wrong_choices + [q["correct"]]
        random.shuffle(choices)
        quiz.append(
            {
                "question": q["question"],
                "correct": q["correct"],
                "choices": choices,
                "explanations": q.get("explanations", {}),
            }
        )
    return quiz


# ============================================================
# セッション状態の初期化
# ============================================================
def init_state():
    defaults = {
        "stage": "start",  # start -> quiz -> result
        "quiz": [],
        "current": 0,
        "log": [],
        "answered": False,
        "selected_choice": None,
        "start_time": None,
        "sound_played": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_quiz():
    st.session_state.stage = "start"
    st.session_state.quiz = []
    st.session_state.current = 0
    st.session_state.log = []
    st.session_state.answered = False
    st.session_state.selected_choice = None
    st.session_state.start_time = None
    st.session_state.sound_played = True


def get_remaining_seconds() -> float:
    if st.session_state.start_time is None:
        return TIME_LIMIT_SECONDS
    elapsed = time.time() - st.session_state.start_time
    return TIME_LIMIT_SECONDS - elapsed


# ============================================================
# 画面：スタート
# ============================================================
def render_start():
    st.title(QUIZ_TITLE)
    st.write("中学受験対策の社会科（地理）4択クイズです。ボタンをクリックして答えを選んでください。")
    st.write(f"現在、問題は全部で **{len(QUESTIONS)}問** 登録されています。")
    st.info(f"⏱ 制限時間は全体で **{TIME_LIMIT_SECONDS // 60}分** です。時間になると自動で結果画面に切り替わります。")

    max_q = len(QUESTIONS)
    if max_q > 1:
        num = st.slider("何問挑戦しますか？", min_value=1, max_value=max_q, value=max_q)
    else:
        num = max_q
        st.write("挑戦する問題数: 1問")

    if st.button("クイズをスタートする", type="primary", use_container_width=True):
        st.session_state.quiz = generate_quiz(num)
        st.session_state.current = 0
        st.session_state.log = []
        st.session_state.answered = False
        st.session_state.selected_choice = None
        st.session_state.start_time = time.time()
        st.session_state.sound_played = True
        st.session_state.stage = "quiz"
        st.rerun()


# ============================================================
# 画面：出題中
# ============================================================
def render_quiz():
    quiz = st.session_state.quiz
    total = len(quiz)
    current = st.session_state.current

    # 制限時間チェック（全問終わっていなくても、時間切れなら結果画面へ）
    remaining = get_remaining_seconds()
    if remaining <= 0 or current >= total:
        st.session_state.stage = "result"
        st.rerun()
        return

    # ---- 残り時間の表示（毎秒更新） ----
    timer_color = "red" if remaining <= 30 else "inherit"
    st.markdown(
        f"<div style='text-align:right; font-size:1.3em; font-weight:bold; "
        f"color:{timer_color};'>⏱ 残り時間 {format_mmss(remaining)}</div>",
        unsafe_allow_html=True,
    )

    q = quiz[current]

    st.progress(current / total)
    st.caption(f"第 {current + 1} 問 / 全 {total} 問")
    st.subheader(q["question"])

    if not st.session_state.answered:
        for i, choice in enumerate(q["choices"]):
            if st.button(choice, key=f"choice_{current}_{i}", use_container_width=True):
                is_correct = choice == q["correct"]
                st.session_state.selected_choice = choice
                st.session_state.answered = True
                st.session_state.sound_played = False
                st.session_state.log.append(
                    {
                        "問題": q["question"],
                        "あなたの回答": choice,
                        "正解": q["correct"],
                        "結果": "○" if is_correct else "×",
                        "is_correct": is_correct,
                    }
                )
                st.rerun()
    else:
        last = st.session_state.log[-1]

        # 効果音は答えた直後の1回だけ鳴らす（タイマー更新のたびに鳴らさない）
        if not st.session_state.sound_played:
            play_sound_effect(generate_ding_sound() if last["is_correct"] else generate_buzzer_sound())
            st.session_state.sound_played = True

        if last["is_correct"]:
            st.success(f"○ あなたの回答「{last['あなたの回答']}」")
        else:
            st.error(f"× あなたの回答「{last['あなたの回答']}」")

        button_label = "次の問題へ" if current + 1 < total else "結果を見る"
        if st.button(button_label, type="primary", use_container_width=True):
            st.session_state.current += 1
            st.session_state.answered = False
            st.session_state.selected_choice = None
            if st.session_state.current >= total:
                st.session_state.stage = "result"
            st.rerun()
            return

    # ここまで来た（＝ボタンが押されなかった）場合は、1秒待ってから
    # 画面を再描画し、残り時間の表示をリアルタイムに近い形で更新し続ける。
    time.sleep(1)
    st.rerun()


# ============================================================
# 画面：結果
# ============================================================
def render_result():
    log = st.session_state.log
    total = len(log)
    correct_count = sum(1 for item in log if item["is_correct"])
    incorrect_count = total - correct_count
    accuracy = (correct_count / total * 100) if total else 0

    st.title("結果発表")
    st.write(f"正解率: **{accuracy:.1f}%** （{correct_count} / {total} 問正解）")

    fig, ax = plt.subplots(figsize=(4, 4))
    if total > 0:
        ax.pie(
            [correct_count, incorrect_count],
            labels=["正解", "不正解"],
            autopct="%1.1f%%",
            colors=["#4CAF50", "#F44336"],
            startangle=90,
        )
    ax.axis("equal")
    st.pyplot(fig, use_container_width=False)
    plt.close(fig)

    st.subheader("解いた問題の一覧")
    df = pd.DataFrame(log)[["問題", "あなたの回答", "正解", "結果"]]
    st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("もう一度挑戦する", type="primary", use_container_width=True):
        reset_quiz()
        st.rerun()


# ============================================================
# メイン
# ============================================================
def main():
    st.set_page_config(page_title=QUIZ_TITLE, page_icon="🗾", layout="centered")
    init_state()

    if st.session_state.stage == "start":
        render_start()
    elif st.session_state.stage == "quiz":
        render_quiz()
    elif st.session_state.stage == "result":
        render_result()


if __name__ == "__main__":
    main()
