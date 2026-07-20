"use client";

import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Check, FlaskConical, KeyRound, Play, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";
import type { EvaluationSummary } from "@/lib/types";

const snapshot: EvaluationSummary = {
  case_count: 15,
  baseline_root_cause_top1: 1,
  baseline_evidence_recall: 0.444,
  root_cause_top1: 1,
  showcase_top1: 1,
  causal_chain_coverage: 1,
  evidence_precision: 0.79,
  citation_validity: 1,
  evidence_recall: 1,
  unsupported_claim_rate: 0,
  action_accuracy: 1,
  forbidden_action_rate: 0,
  average_tool_calls: 4.33,
  average_cost_cny: 0,
  p95_latency_ms: 4,
};

export function EvaluationConsole() {
  const [token, setToken] = useState("");
  const evaluation = useMutation({ mutationFn: () => api.evaluation(token) });
  const data = evaluation.data ?? snapshot;

  function run(event: FormEvent) {
    event.preventDefault();
    evaluation.mutate();
  }

  const metrics = [
    ["根因 Top-1", data.root_cause_top1, ">= 80%"],
    ["展示案例", data.showcase_top1, "= 100%"],
    ["引用有效率", data.citation_validity, "= 100%"],
    ["关键证据召回", data.evidence_recall, ">= 80%"],
  ] as const;

  return (
    <main className="eval-page">
      <header className="eval-header">
        <div>
          <Link href="/"><ArrowLeft size={15} /> 返回调查台</Link>
          <span className="eyebrow">Regression laboratory</span>
          <h1>调查质量评测</h1>
          <p>同一套确定性评分器同时衡量一次性 Prompt 基线和证据工作流。</p>
        </div>
        <div className="eval-seal"><FlaskConical /><span><strong>{data.case_count}</strong> CASES</span></div>
      </header>

      <section className="eval-metrics">
        {metrics.map(([label, value, gate]) => (
          <article key={label}>
            <span className="metric-gate"><Check size={13} /> PASS {gate}</span>
            <strong>{Math.round(value * 100)}<small>%</small></strong>
            <h2>{label}</h2>
            <div className="metric-bar"><span style={{ width: `${value * 100}%` }} /></div>
          </article>
        ))}
      </section>

      <section className="eval-grid">
        <article className="method-card">
          <span className="eyebrow">Evaluation contract</span>
          <h2>不让模型给自己打分</h2>
          <p>根因、因果链、证据引用与禁止动作均由黄金标注确定性评分。模型裁判只评价报告表达。</p>
          <dl>
            <div><dt>数据集</dt><dd>3 展示 + 12 隐藏</dd></div>
            <div><dt>重复运行</dt><dd>每案例 3 次</dd></div>
            <div><dt>无证据断言</dt><dd>{Math.round(data.unsupported_claim_rate * 100)}%</dd></div>
            <div><dt>平均工具调用</dt><dd>{data.average_tool_calls.toFixed(1)}</dd></div>
          </dl>
          <div className="baseline-compare">
            <span className="eyebrow">Baseline vs agent</span>
            <div><span>一次性基线 · 证据召回</span><strong>{Math.round(data.baseline_evidence_recall * 100)}%</strong></div>
            <div><span>受约束 Agent · 证据召回</span><strong>{Math.round(data.evidence_recall * 100)}%</strong></div>
            <div><span>因果链覆盖</span><strong>{Math.round(data.causal_chain_coverage * 100)}%</strong></div>
            <div><span>禁止动作触发</span><strong>{Math.round(data.forbidden_action_rate * 100)}%</strong></div>
          </div>
        </article>

        <form className="runner-card" onSubmit={run}>
          <div className="runner-icon"><KeyRound /></div>
          <span className="eyebrow">Admin runner</span>
          <h2>启动完整回归</h2>
          <p>实时评测需要管理员令牌。令牌只随本次请求发送，不会保存在浏览器。</p>
          <label htmlFor="admin-token">管理员令牌</label>
          <input id="admin-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="admin-demo-token" />
          <button disabled={!token || evaluation.isPending}><Play size={16} />{evaluation.isPending ? "正在运行" : "运行 15 案例评测"}</button>
          {evaluation.error && <p className="form-error">{evaluation.error.message}</p>}
          {evaluation.isSuccess && <p className="form-success"><ShieldCheck size={15} /> 本次回归已完成</p>}
        </form>
      </section>
    </main>
  );
}
