from __future__ import annotations

from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.services.stats_analytics import ScorePoint, linear_regression_slope, rolling_mean


def _plot_one_axis(ax, title: str, points: list[ScorePoint]) -> None:
    ax.set_title(title)
    ax.set_ylim(0, 3)
    ax.set_ylabel("Оценка")
    ax.grid(alpha=0.25)

    if not points:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center", transform=ax.transAxes)
        return

    y = [p.score for p in points]
    x = list(range(1, len(y) + 1))

    ax.plot(x, y, marker="o", linewidth=1.5, label="Факт")

    smooth = rolling_mean(y, window=5)
    ax.plot(x, smooth, linestyle="--", linewidth=2, label="Скользящее среднее (5)")

    slope = linear_regression_slope(y)
    mean_y = sum(y) / len(y)
    mean_x = sum(x) / len(x)
    trend_line = [mean_y + slope * (xi - mean_x) for xi in x]
    ax.plot(x, trend_line, linewidth=2, label=f"Тренд (slope={slope:+.3f})")

    ax.set_xticks(x)
    ax.legend(fontsize=8)


def build_user_stats_png(candidate_points: list[ScorePoint], interviewer_points: list[ScorePoint]) -> bytes:
    fig, axes = plt.subplots(2, 1, figsize=(10, 8), constrained_layout=True)

    _plot_one_axis(axes[0], "Динамика как кандидат (оценки от интервьюеров)", candidate_points)
    _plot_one_axis(axes[1], "Динамика как интервьюер (оценки от кандидатов)", interviewer_points)

    axes[1].set_xlabel("Номер собеса по времени")
    fig.suptitle("Статистика оценок по последним собесам", fontsize=14)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=140)
    plt.close(fig)
    return buf.getvalue()
