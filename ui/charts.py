"""Plotly helpers styled to match the PulseBand design tokens."""

from __future__ import annotations

import plotly.graph_objects as go

from ui.styles import INK, LINE, MUTED, TEAL

FONT = dict(family="Source Sans 3, system-ui, sans-serif", color=INK, size=13)


def _layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=16, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=FONT,
        showlegend=False,
    )
    fig.update_xaxes(gridcolor=LINE, zeroline=False, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=LINE, zeroline=False, tickfont=dict(color=MUTED))
    return fig


def hbar(labels: list[str], values: list[float], *, colors: list[str] | None = None,
         text: list[str] | None = None, height: int = 260, x_range=None) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors or TEAL,
        text=text or [str(v) for v in values], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True, ticksuffix="  ")
    fig.update_xaxes(showticklabels=False, showgrid=False,
                     range=x_range or [0, max(values, default=1) * 1.3])
    fig = _layout(fig, height)
    fig.update_layout(margin=dict(l=150, r=24, t=8, b=8))
    return fig


def heatmap(z: list[list[int]], x: list[str], y: list[str], height: int = 380) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=z, x=x, y=y,
        colorscale=[[0, "#F3F5F6"], [0.0001, "#D7EAE8"], [1, TEAL]],
        text=[[str(v) if v else "" for v in row] for row in z], texttemplate="%{text}",
        showscale=False, xgap=2, ygap=2,
        hovertemplate="Expected %{y}<br>Predicted %{x}<br>%{z} case(s)<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", title="Expected", showgrid=False, automargin=True)
    fig.update_xaxes(title="Predicted by AI", side="top", showgrid=False, automargin=True,
                     tickangle=-30)
    fig = _layout(fig, height)
    fig.update_layout(margin=dict(l=150, r=8, t=90, b=8))
    return fig
