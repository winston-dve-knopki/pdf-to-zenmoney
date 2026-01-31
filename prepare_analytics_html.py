"""
Генерация одностраничного HTML с аналитикой по CSV транзакциям ZenMoney.
Читает все CSV в репозитории, строит графики Plotly и сохраняет один HTML файл.
"""
from pathlib import Path
import argparse
from typing import List

import pandas as pd
import plotly.graph_objects as go

# Имя категории для пустых/без категории
OTHER_CAT_LABEL = "Остальное"
NO_CATEGORY_LABEL = "Без категории"


def _str_safe(val, max_len: int = 0):
    """Приводит значение к строке (API/CSV могут отдавать NaN, float, None)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        s = ""
    else:
        s = str(val)
    return (s[:max_len] if max_len else s).replace("\n", " ")


def find_csv_files(root: Path) -> List[Path]:
    """Находит все CSV файлы в директории и поддиректориях."""
    root = Path(root).resolve()
    return sorted(root.rglob("*.csv"))


def load_all_csv(paths: List[Path]) -> pd.DataFrame:
    """Загружает и объединяет все CSV (разделитель ;, utf-8-sig). Имена колонок приводятся к нижнему регистру."""
    frames = []
    for p in paths:
        try:
            df = pd.read_csv(p, sep=";", encoding="utf-8-sig", dtype=str)
            df.columns = [c.strip().lower() if isinstance(c, str) else c for c in df.columns]
            df["_source"] = p.name
            frames.append(df)
        except Exception as e:
            print(f"Пропуск {p}: {e}")
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Приводит типы: дата, числа; нормализует категории."""
    if df.empty:
        return df
    df = df.copy()
    # Дата
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    # Числа
    for col in ("income", "outcome", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    # Категория: пустая -> "Без категории" (API/CSV могут отдавать NaN, float)
    if "category" not in df.columns:
        df["category"] = NO_CATEGORY_LABEL
    else:
        df["category"] = df["category"].apply(
            lambda x: NO_CATEGORY_LABEL if (x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == "") else str(x).strip()
        )
    return df


def top_categories(df: pd.DataFrame, top_n: int, by_col: str = "outcome") -> List[str]:
    """Список топ-N категорий по сумме трат (outcome)."""
    if df.empty or by_col not in df.columns:
        return []
    agg = df.groupby("category", as_index=False)[by_col].sum()
    agg = agg.sort_values(by_col, ascending=False)
    return agg["category"].head(top_n).tolist()


def make_weekly_outcome_by_category_bar(df: pd.DataFrame, min_outcome_per_week: float = 5000) -> go.Figure:
    """Понедельный bar: расходы по неделям по категориям. Только категории, где в неделю было > min_outcome_per_week."""
    if df.empty:
        return go.Figure()
    expenses = df[df["outcome"] > 0].copy()
    if expenses.empty:
        return go.Figure()
    expenses["week"] = expenses["date"].dt.to_period("W").dt.to_timestamp()
    agg = expenses.groupby(["week", "category"], as_index=False)["outcome"].sum()
    # Оставляем только категории, у которых хотя бы в одной неделе траты > min_outcome_per_week
    cat_above = agg[agg["outcome"] >= min_outcome_per_week]["category"].unique()
    agg = agg[agg["category"].isin(cat_above)]
    if agg.empty:
        return go.Figure()
    weeks = sorted(agg["week"].unique())
    categories = sorted(agg["category"].unique())
    fig = go.Figure()
    for cat in categories:
        cat_df = agg[agg["category"] == cat]
        by_week = cat_df.set_index("week")["outcome"]
        y = [float(by_week.get(w, 0)) / 1000 for w in weeks]
        fig.add_trace(
            go.Bar(
                x=weeks,
                y=y,
                name=cat,
                customdata=[cat] * len(weeks),
                text=[f"{v:.1f}" if v else "" for v in y],
                textposition="inside",
                hovertemplate="%{customdata}<br>%{y:.1f} тыс ₽<extra></extra>",
            )
        )
    fig.update_layout(
        title="Расходы по неделям по категориям (категории с тратами > 5 тыс ₽ в неделю)",
        xaxis_title="Неделя",
        yaxis_title="Сумма, тыс. ₽",
        barmode="stack",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        margin=dict(t=60, b=50),
        height=400,
    )
    return fig


def make_bar_plot(category_totals: pd.DataFrame, title: str = "Расходы по категориям") -> go.Figure:
    """Горизонтальный bar по категориям. Длина столбца = сумма в тыс. ₽, ось X от 0."""
    if category_totals.empty:
        return go.Figure()
    cat = category_totals.sort_values("outcome", ascending=True).copy()
    # Сумма в рублях -> в тысячах для оси X; длина столбца равна значению в тыс. ₽
    cat["outcome_thous"] = (cat["outcome"].astype(float) / 1000).round(2)
    x_vals = cat["outcome_thous"].tolist()
    fig = go.Figure(
        go.Bar(
            y=cat["category"].tolist(),
            x=x_vals,
            orientation="h",
            text=[f"{v:,.1f} тыс" for v in x_vals],
            textposition="outside",
        )
    )
    x_max = max(x_vals) if x_vals else 1
    fig.update_layout(
        title=title,
        xaxis_title="Сумма, тыс. ₽",
        yaxis_title="",
        xaxis=dict(range=[0, x_max * 1.15], dtick=None),
        margin=dict(t=50, b=50),
        height=max(300, len(cat) * 22),
    )
    return fig


def make_summary_html(total_income: float, total_outcome: float) -> str:
    """HTML блок: сумма доходов и расходов."""
    return f"""
    <div class="summary-block">
        <div class="summary-item income">
            <span class="label">Доходы</span>
            <span class="value">{total_income:,.0f} ₽</span>
        </div>
        <div class="summary-item outcome">
            <span class="label">Расходы</span>
            <span class="value">−{total_outcome:,.0f} ₽</span>
        </div>
        <div class="summary-item balance">
            <span class="label">Баланс</span>
            <span class="value">{total_income - total_outcome:,.0f} ₽</span>
        </div>
    </div>
    """


def make_table_html(
    df: pd.DataFrame,
    top_cats: List[str],
    top_per_cat: int = 10,
) -> str:
    """Таблица: топ категории + топ трат в каждой из них."""
    if df.empty:
        return "<p>Нет данных</p>"
    expenses = df[df["outcome"] > 0].copy()
    if expenses.empty:
        return "<p>Нет расходов</p>"
    expenses = expenses[expenses["category"].isin(top_cats)]
    if expenses.empty:
        return "<p>Нет расходов в выбранных категориях</p>"
    cat_totals = expenses.groupby("category", as_index=False)["outcome"].sum()
    cat_totals = cat_totals.sort_values("outcome", ascending=False)
    rows = []
    for _, row in cat_totals.iterrows():
        cat = row["category"]
        total = row["outcome"]
        rows.append(f'<tr class="cat-row"><td colspan="4"><strong>{cat}</strong> — всего {total:,.0f} ₽</td></tr>')
        top_tx = expenses[expenses["category"] == cat].nlargest(top_per_cat, "outcome")
        for _, t in top_tx.iterrows():
            date_val = t.get("date")
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") and pd.notna(date_val) else ""
            outcome_val = t.get("outcome", 0)
            try:
                outcome_fmt = f"{float(outcome_val):,.0f}"
            except (TypeError, ValueError):
                outcome_fmt = _str_safe(outcome_val)
            comment = _str_safe(t.get("comment"), 60)
            payee = _str_safe(t.get("payee"), 40)
            rows.append(
                f'<tr><td>{date_str}</td><td>{outcome_fmt}</td><td>{payee}</td><td>{comment}</td></tr>'
            )
    table_body = "\n".join(rows)
    return f"""
    <div class="table-wrap">
        <table class="tx-table">
            <thead><tr><th>Дата</th><th>Сумма</th><th>Получатель</th><th>Комментарий</th></tr></thead>
            <tbody>{table_body}</tbody>
        </table>
    </div>
    """


def build_html(
    df: pd.DataFrame,
    top_n: int,
    output_path: Path,
    plotly_cdn: bool = True,
) -> None:
    """Собирает одностраничный HTML с графиками и таблицей."""
    if df.empty:
        raise ValueError("Нет данных для построения отчёта")
    df = prepare_data(df)
    expenses = df[df["outcome"] > 0]
    total_income = df["income"].sum()
    total_outcome = df["outcome"].sum()

    # 1. Расходы по неделям по категориям (только категории с тратами > 5к в неделю)
    fig_weekly_outcome = make_weekly_outcome_by_category_bar(df, min_outcome_per_week=5000)
    # 2. Bar по категориям (итого), длина столбца = сумма в тыс. ₽
    cat_totals = expenses.groupby("category", as_index=False)["outcome"].sum()
    cat_totals = cat_totals.sort_values("outcome", ascending=False)
    fig_bar = make_bar_plot(cat_totals)

    plot_weekly_outcome = fig_weekly_outcome.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": True})
    plot_bar = fig_bar.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": True})

    summary_html = make_summary_html(total_income, total_outcome)
    # Таблица: 5 категорий, по 3 транзакции в каждой
    table_top_cats = top_categories(expenses, top_n=5)
    if not table_top_cats:
        table_top_cats = [NO_CATEGORY_LABEL]
    table_html = make_table_html(df, table_top_cats, top_per_cat=3)

    plotly_script = (
        '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
        if plotly_cdn
        else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Аналитика ZenMoney</title>
    {plotly_script if plotly_cdn else ""}
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        h1 {{ margin-top: 0; }}
        .filters {{ margin-bottom: 20px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
        .filters button {{ padding: 8px 16px; cursor: pointer; border-radius: 8px; border: 1px solid #ccc; background: #fff; }}
        .filters button.active {{ background: #1a73e8; color: #fff; border-color: #1a73e8; }}
        .summary-block {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 24px; }}
        .summary-item {{ background: #fff; padding: 16px 24px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 160px; }}
        .summary-item .label {{ display: block; color: #666; font-size: 14px; }}
        .summary-item .value {{ font-size: 24px; font-weight: 600; }}
        .summary-item.income .value {{ color: #0d7d43; }}
        .summary-item.outcome .value {{ color: #c5221f; }}
        .chart-wrap {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .chart-wrap h2 {{ margin: 0 0 12px 0; font-size: 18px; }}
        .table-wrap {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow-x: auto; }}
        .tx-table {{ width: 100%; border-collapse: collapse; }}
        .tx-table th, .tx-table td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
        .tx-table th {{ background: #f8f9fa; font-weight: 600; }}
        .tx-table .cat-row td {{ background: #f0f4f8; font-weight: 500; }}
    </style>
</head>
<body>
    <h1>Аналитика расходов ZenMoney</h1>
    <p>Данные загружены из CSV. В таблице: топ 5 категорий по расходам, по 3 транзакции в каждой.</p>

    {summary_html}

    <div class="chart-wrap">
        <h2>Расходы по неделям по категориям</h2>
        {plot_weekly_outcome}
    </div>

    <div class="chart-wrap">
        <h2>Соотношение по категориям (итого)</h2>
        {plot_bar}
    </div>

    <div class="table-wrap">
        <h2>Топ категории и крупные траты</h2>
        {table_html}
    </div>
</body>
</html>
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Сохранено: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Генерация HTML с аналитикой по CSV транзакциям ZenMoney"
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("."),
        help="Директория для поиска CSV (по умолчанию текущая)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("analytics.html"),
        help="Выходной HTML файл (по умолчанию analytics.html)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Топ N категорий для area chart (остальное в «Остальное»). По умолчанию 3",
    )
    parser.add_argument(
        "--no-cdn",
        action="store_true",
        help="Встроить plotly.js в файл (файл будет больше, но работает офлайн)",
    )
    args = parser.parse_args()

    paths = find_csv_files(args.csv_dir)
    if not paths:
        print("CSV файлы не найдены")
        return 1
    print(f"Найдено CSV: {len(paths)}")
    df = load_all_csv(paths)
    if df.empty:
        print("Нет данных для отчёта")
        return 1
    print(f"Загружено строк: {len(df)}")
    build_html(df, top_n=args.top, output_path=args.output, plotly_cdn=not args.no_cdn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
