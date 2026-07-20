"use client";

import * as echarts from "echarts";
import { useEffect, useRef } from "react";

function numberSeries(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is number => typeof item === "number");
}

export function MetricEvidenceChart({ attributes }: { attributes: Record<string, unknown> }) {
  const element = useRef<HTMLDivElement>(null);
  const series = numberSeries(attributes.series);

  useEffect(() => {
    if (!element.current || series.length < 2) return;
    const chart = echarts.init(element.current, undefined, { renderer: "svg" });
    const anomalyIndex =
      typeof attributes.anomaly_index === "number" ? attributes.anomaly_index : -1;
    chart.setOption({
      animation: false,
      grid: { left: 42, right: 18, top: 24, bottom: 30 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: series.map((_, index) => `T${index + 1}`),
        axisLine: { lineStyle: { color: "#8fa29d" } },
        axisLabel: { color: "#607077", fontFamily: "monospace", fontSize: 9 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#d6dfdc", type: "dashed" } },
        axisLabel: { color: "#607077", fontFamily: "monospace", fontSize: 9 },
      },
      series: [
        {
          type: "line",
          data: series,
          symbolSize: 7,
          lineStyle: { color: "#1e5eff", width: 2 },
          itemStyle: {
            color: (params: { dataIndex: number }) =>
              params.dataIndex >= anomalyIndex && anomalyIndex >= 0 ? "#c74d2d" : "#1e5eff",
          },
          areaStyle: { color: "rgba(30,94,255,.09)" },
        },
      ],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [attributes.anomaly_index, series]);

  if (series.length < 2) return null;
  return (
    <section className="evidence-visual" aria-label="指标趋势图">
      <header><span>METRIC TREND</span><strong>{String(attributes.metric_name ?? "metric")}</strong></header>
      <div ref={element} className="metric-chart" />
    </section>
  );
}

interface TraceSpan {
  name: string;
  start_ms: number;
  duration_ms: number;
}

function traceSpans(value: unknown): TraceSpan[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is TraceSpan =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as Record<string, unknown>).name === "string" &&
      typeof (item as Record<string, unknown>).start_ms === "number" &&
      typeof (item as Record<string, unknown>).duration_ms === "number",
  );
}

export function TraceWaterfall({ attributes }: { attributes: Record<string, unknown> }) {
  const spans = traceSpans(attributes.spans);
  if (!spans.length) return null;
  const end = Math.max(...spans.map((span) => span.start_ms + span.duration_ms), 1);
  return (
    <section className="evidence-visual trace-visual" aria-label="Trace 瀑布图">
      <header><span>TRACE WATERFALL</span><strong>{String(attributes.trace_id ?? "trace")}</strong></header>
      <div className="waterfall-scale"><span>0 ms</span><span>{end} ms</span></div>
      {spans.map((span, index) => (
        <div className="waterfall-row" key={`${span.name}-${index}`}>
          <span>{span.name}</span>
          <div><i style={{ left: `${(span.start_ms / end) * 100}%`, width: `${Math.max((span.duration_ms / end) * 100, 2)}%` }} /></div>
          <small>{span.duration_ms} ms</small>
        </div>
      ))}
    </section>
  );
}
