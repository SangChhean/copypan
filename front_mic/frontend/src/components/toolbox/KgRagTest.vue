<script setup>
import { ref, onMounted } from "vue";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { message } from "ant-design-vue";
import { toastSuccess } from "../utils/Dialog";

const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const activeTab = ref("query");

function getAuthHeaders() {
  const token = localStorage.getItem("token") || null;
  if (!token) {
    window.location.hash = "/login";
    return null;
  }
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

// ---------- 健康状态 ----------
const healthLoading = ref(false);
const health = ref(null);

async function fetchHealth() {
  const headers = getAuthHeaders();
  if (!headers) return;
  healthLoading.value = true;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/health`, { headers });
    health.value = res.data;
  } catch (e) {
    health.value = null;
    message.error(e.response?.data?.error || e.message || "健康检查失败");
  } finally {
    healthLoading.value = false;
  }
}

// ---------- Tab 1：全流程查询 ----------
const queryText = ref("");
const queryLoading = ref(false);
const queryResult = ref(null);

// 14 个可调参数（与 DEFAULT_PARAMS 对齐）
const params = ref({
  bm25_top_k: 30,
  dense_top_k: 30,
  num_candidates: 100,
  rrf_k: 60,
  bm25_weight: 1,
  dense_weight: 1,
  rerank_top_n: 20,
  skeleton_score_threshold: 0.5,
  skeleton_top_n: 5,
  skeleton_route_top_k: 5,
  temperature: 0.3,
  llm_model: "claude-sonnet-4-20250514",
  skip_query_rewrite: false,
  skip_generation: false,
});

const llmModelOptions = [
  { label: "claude-sonnet-4-20250514", value: "claude-sonnet-4-20250514" },
  { label: "claude-haiku-4-5-20251001", value: "claude-haiku-4-5-20251001" },
];

async function runFullQuery() {
  const q = (queryText.value || "").trim();
  if (!q) {
    message.warning("请输入查询问题");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  queryLoading.value = true;
  queryResult.value = null;
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/query`,
      { query: q, params: params.value },
      { headers }
    );
    queryResult.value = res.data;
    toastSuccess("查询完成");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "查询失败");
  } finally {
    queryLoading.value = false;
  }
}

// 骨架格式化显示（与后端 _format_skeleton 一致）
function formatSkeleton(skeleton) {
  if (!skeleton) return "";
  if (skeleton.root && skeleton.branches) {
    return skeleton.branches
      .map((b) => {
        const rel = b.relation_str || `${skeleton.root} —[${b.relation_type || "相关"}]— ${b.name}`;
        return `${rel} (${Number(b.score || 0).toFixed(3)})`;
      })
      .join("\n");
  }
  if (skeleton.roots && skeleton.branches) {
    return skeleton.branches
      .map((b) => {
        const rel = b.relation_str || `${b.root} —[${b.relation_type || "相关"}]— ${b.name}`;
        return `${rel} (${Number(b.score || 0).toFixed(3)})`;
      })
      .join("\n");
  }
  return JSON.stringify(skeleton);
}

function chunkPreview(text, maxLen = 200) {
  if (!text || typeof text !== "string") return "";
  return text.length <= maxLen ? text : text.slice(0, maxLen) + "…";
}

// ---------- Tab 2：图谱浏览器 ----------
const graphMode = ref("explore"); // explore | path | stats
const exploreConcept = ref("");
const exploreHops = ref(1);
const pathConceptA = ref("");
const pathConceptB = ref("");
const pathMaxHops = ref(3);
const graphLoading = ref(false);
const exploreResult = ref(null);
const pathResult = ref(null);
const statsResult = ref(null);

/** Tab2 邻居表列：关系列用 rel_from ──type──► rel_to 展示 */
const neighborTableColumns = [
  { title: "邻居", dataIndex: "neighbor", key: "neighbor" },
  { title: "关系", key: "edge" },
];

function formatNeighborEdge(record) {
  if (record.relations && record.relations.length) {
    return record.relations.join(" ／ ");
  }
  return record.relation_type || "相关";
}

async function runExplore() {
  const c = (exploreConcept.value || "").trim();
  if (!c) {
    message.warning("请输入概念名称");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  graphLoading.value = true;
  exploreResult.value = null;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/graph/explore`, {
      headers,
      params: { concept: c, hops: exploreHops.value },
    });
    exploreResult.value = res.data;
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "邻居查询失败");
  } finally {
    graphLoading.value = false;
  }
}

async function runPath() {
  const a = (pathConceptA.value || "").trim();
  const b = (pathConceptB.value || "").trim();
  if (!a || !b) {
    message.warning("请输入起点和终点概念");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  graphLoading.value = true;
  pathResult.value = null;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/graph/path`, {
      headers,
      params: { concept_a: a, concept_b: b, max_hops: pathMaxHops.value },
    });
    pathResult.value = res.data;
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "路径查询失败");
  } finally {
    graphLoading.value = false;
  }
}

async function runStats() {
  const headers = getAuthHeaders();
  if (!headers) return;
  graphLoading.value = true;
  statsResult.value = null;
  try {
    const res = await axios.get(`${apiBase}/api/kg_rag/graph/stats`, { headers });
    statsResult.value = res.data;
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "图谱统计失败");
  } finally {
    graphLoading.value = false;
  }
}

function pathSegmentDisplay(pathItem) {
  const nodes = pathItem.path_nodes || [];
  const rels = pathItem.relations || [];
  const parts = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    const rel = rels[i];
    const relType = (rel && typeof rel === "object") ? (rel.type || "相关") : (rel || "相关");
    const forward = (rel && typeof rel === "object") ? rel.forward !== false : true;
    if (forward) {
      parts.push(nodes[i]);
      parts.push(` ──${relType}──► `);
    } else {
      parts.push(nodes[i]);
      parts.push(` ◄──${relType}── `);
    }
  }
  if (nodes.length) parts.push(nodes[nodes.length - 1]);
  return parts.join("");
}

// ---------- Tab 3：单独检索测试 ----------
const searchOnlyQuery = ref("");
const searchOnlyModes = ref([]); // 'route1' | 'route2' | 'route12' | 'route3' | 'all'
const route3Concept = ref("");
const searchOnlyTopK = ref(20);
const searchOnlyRrfK = ref(60);
const searchOnlyLoading = ref(false);
const searchOnlyResult = ref(null);

const searchOnlyModeOptions = [
  { label: "路1（BM25）", value: "route1" },
  { label: "路2（Dense）", value: "route2" },
  { label: "路1+路2（RRF 融合）", value: "route12" },
  { label: "路3（骨架扩展）", value: "route3" },
  { label: "全部", value: "all" },
];

function getSearchOnlyParams() {
  const modes = searchOnlyModes.value;
  const has1 = modes.includes("route1") || modes.includes("route12") || modes.includes("all");
  const has2 = modes.includes("route2") || modes.includes("route12") || modes.includes("all");
  return {
    skip_generation: true,
    rerank_top_n: searchOnlyTopK.value,
    rrf_k: searchOnlyRrfK.value,
    bm25_top_k: has1 ? searchOnlyTopK.value : 0,
    dense_top_k: has2 ? searchOnlyTopK.value : 0,
  };
}

async function runSearchOnly() {
  const q = (searchOnlyQuery.value || "").trim();
  if (!q) {
    message.warning("请输入查询");
    return;
  }
  if (searchOnlyModes.value.length === 0) {
    message.warning("请至少选择一种检索模式");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  searchOnlyLoading.value = true;
  searchOnlyResult.value = null;
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/query`,
      { query: q, params: getSearchOnlyParams() },
      { headers }
    );
    searchOnlyResult.value = res.data;
    toastSuccess("检索完成");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "检索失败");
  } finally {
    searchOnlyLoading.value = false;
  }
}

function getSearchOnlyColumns() {
  const modes = searchOnlyModes.value;
  const step3 = searchOnlyResult.value?.steps?.step3;
  if (!step3) return [];
  const cols = [];
  if (modes.includes("route1") || modes.includes("all")) cols.push({ key: "bm25", title: "路1 BM25", data: step3.bm25_results || [] });
  if (modes.includes("route2") || modes.includes("all")) cols.push({ key: "dense", title: "路2 Dense", data: step3.dense_results || [] });
  if (modes.includes("route12") || modes.includes("all")) cols.push({ key: "main", title: "路1+路2 RRF", data: step3.main_results || [] });
  if (modes.includes("route3") || modes.includes("all")) cols.push({ key: "route3", title: "路3 骨架扩展", data: step3.expanded_results || [] });
  return cols;
}

function chunkIdSets() {
  const cols = getSearchOnlyColumns();
  const idToCount = {};
  cols.forEach((col) => {
    (col.data || []).forEach((r) => {
      const id = r.chunk_id;
      if (id) idToCount[id] = (idToCount[id] || 0) + 1;
    });
  });
  return Object.keys(idToCount).filter((id) => idToCount[id] > 1);
}

function chunkPreview150(text) {
  if (!text || typeof text !== "string") return "";
  return text.length <= 150 ? text : text.slice(0, 150) + "…";
}

// ---------- Tab 4：Prompt 预览 ----------
const promptPreviewQuery = ref("");
const promptPreviewLoading = ref(false);
const promptPreviewResult = ref(null);

async function runPromptPreview() {
  const q = (promptPreviewQuery.value || "").trim();
  if (!q) {
    message.warning("请输入查询");
    return;
  }
  const headers = getAuthHeaders();
  if (!headers) return;
  promptPreviewLoading.value = true;
  promptPreviewResult.value = null;
  try {
    const res = await axios.post(
      `${apiBase}/api/kg_rag/prompt_preview`,
      { query: q, params: params.value },
      { headers }
    );
    promptPreviewResult.value = res.data;
    toastSuccess("Prompt 已生成");
  } catch (e) {
    message.error(e.response?.data?.error || e.message || "生成失败");
  } finally {
    promptPreviewLoading.value = false;
  }
}

// ---------- 生命周期 ----------
onMounted(() => {
  fetchHealth();
});
</script>

<template>
  <div class="kg-rag-header">
    <div class="header-left" @click="() => (window.location.hash = '/tools')">
      <ArrowLeftOutlined class="header-back" />
    </div>
    <div class="header-title">KG-RAG 测试工作台</div>
    <div class="header-health">
      <template v-if="healthLoading"><span class="health-text">检查中…</span></template>
      <template v-else-if="health">
        <span class="health-item"><span class="health-dot" :class="{ ok: health.elasticsearch?.available }" title="Elasticsearch" /> ES</span>
        <span class="health-item"><span class="health-dot" :class="{ ok: health.neo4j?.available }" title="Neo4j" /> Neo4j</span>
        <a-button type="link" size="small" class="health-refresh" @click="fetchHealth">刷新</a-button>
      </template>
      <template v-else><span class="health-text">—</span></template>
    </div>
  </div>
  <div class="kg-rag-page">
    <a-tabs v-model:activeKey="activeTab" class="main-tabs">
      <!-- Tab 1：全流程查询 -->
      <a-tab-pane key="query" tab="全流程查询">
        <a-card class="tab-card">
          <a-row :gutter="24">
            <a-col :xs="24" :md="10" :lg="9">
              <div class="query-section">
                <a-textarea
                  v-model:value="queryText"
                  placeholder="输入查询问题..."
                  :rows="4"
                  class="query-input"
                />
                <a-collapse class="param-collapse" :default-active-key="['params']">
                  <a-collapse-panel key="params" header="检索参数">
                    <a-row :gutter="[12, 12]">
                      <a-col :span="12"><div class="param-item"><span class="param-label">BM25 Top-K</span><a-input-number v-model:value="params.bm25_top_k" :min="10" :max="100" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Dense Top-K</span><a-input-number v-model:value="params.dense_top_k" :min="10" :max="100" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Num Candidates</span><a-input-number v-model:value="params.num_candidates" :min="50" :max="300" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">RRF K</span><a-input-number v-model:value="params.rrf_k" :min="20" :max="100" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">BM25 权重</span><a-input-number v-model:value="params.bm25_weight" :min="0.1" :max="3" :step="0.1" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Dense 权重</span><a-input-number v-model:value="params.dense_weight" :min="0.1" :max="3" :step="0.1" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Rerank Top-N</span><a-input-number v-model:value="params.rerank_top_n" :min="5" :max="50" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">骨架阈值</span><a-input-number v-model:value="params.skeleton_score_threshold" :min="0" :max="1" :step="0.05" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">骨架 Top-N</span><a-input-number v-model:value="params.skeleton_top_n" :min="1" :max="10" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">路3 Top-K</span><a-input-number v-model:value="params.skeleton_route_top_k" :min="1" :max="20" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">Temperature</span><a-input-number v-model:value="params.temperature" :min="0" :max="1" :step="0.1" size="small" class="param-control" /></div></a-col>
                      <a-col :span="12"><div class="param-item"><span class="param-label">模型</span><a-select v-model:value="params.llm_model" :options="llmModelOptions" size="small" class="param-control param-select" /></div></a-col>
                      <a-col :span="24"><div class="param-item param-checkboxes"><a-checkbox v-model:checked="params.skip_query_rewrite">跳过 Query Rewrite</a-checkbox><a-checkbox v-model:checked="params.skip_generation">跳过生成/仅检索</a-checkbox></div></a-col>
                    </a-row>
                  </a-collapse-panel>
                </a-collapse>
                <a-button type="primary" :loading="queryLoading" class="query-btn" @click="runFullQuery">开始查询</a-button>
              </div>
            </a-col>
            <a-col :xs="24" :md="14" :lg="15">
              <div v-if="!queryResult" class="result-placeholder">执行查询后，结果将在此分步展示。</div>
              <template v-else>
                <a-steps direction="vertical" :current="6" class="result-steps">
                  <a-step title="Step 1 概念抽取">
                    <template #description>
                      <a-card size="small" class="step-card">
                      <div v-if="queryResult.steps?.step1">
                        <a-tag v-for="c in (queryResult.steps.step1.concepts || [])" :key="c">{{ c }}</a-tag>
                        <a-collapse v-if="queryResult.steps.step1.raw_response">
                          <a-collapse-panel key="raw" header="原始 LLM 响应">
                            <pre class="raw-pre">{{ queryResult.steps.step1.raw_response }}</pre>
                          </a-collapse-panel>
                        </a-collapse>
                      </div>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 1.5 概念规范化">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <a-tag v-for="n in (queryResult.steps?.step1_5?.normalized || [])" :key="n" color="green">
                        {{ n }}
                      </a-tag>
                      <a-tag v-for="d in (queryResult.steps?.step1_5?.dropped || [])" :key="d" color="red">
                        {{ d }}（丢弃）
                      </a-tag>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 2 概念骨架">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <template v-if="queryResult.steps?.step2?.skeleton">
                        <pre class="skeleton-pre">{{ formatSkeleton(queryResult.steps.step2.skeleton) }}</pre>
                        <div v-if="(queryResult.steps.step2.expanded_nodes || []).length">
                          扩展节点：<a-tag v-for="e in queryResult.steps.step2.expanded_nodes" :key="e">{{ e }}</a-tag>
                        </div>
                      </template>
                      <template v-else> 无骨架（图谱未命中或不可用） </template>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Query 改写">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <template v-if="(queryResult.steps?.step3?.rewritten_queries || []).length">
                        <div
                          v-for="(rq, ri) in queryResult.steps.step3.rewritten_queries"
                          :key="ri"
                          class="rewritten-query-text"
                        >{{ ri + 1 }}. {{ rq }}</div>
                      </template>
                      <div v-else class="rewritten-query-text">—（跳过改写）</div>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 3 检索结果">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <a-tabs size="small">
                        <a-tab-pane key="main" tab="主检索结果">
                          <div
                            v-for="(r, i) in (queryResult.steps?.step3?.main_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">
                              #{{ i + 1 }} · {{ r.chunk_id }} · score {{ (r.score != null ? r.score : r._score).toFixed(3) }}
                              <a-tag
                                v-if="r.source_routes && r.source_routes.length"
                                :color="r.source_routes.length === 2 ? 'orange' : r.source_routes[0] === 'bm25' ? 'blue' : 'green'"
                                class="source-route-tag"
                              >{{ r.source_routes.length === 2 ? 'BM25+Dense' : r.source_routes[0] === 'bm25' ? 'BM25' : 'Dense' }}</a-tag>
                            </div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.book_title || r.message_title" class="chunk-meta">
                              {{ r.book_title }} / {{ r.message_title }} / {{ r.section_title }}
                            </div>
                          </div>
                        </a-tab-pane>
                        <a-tab-pane key="bm25" tab="BM25 原始">
                          <div
                            v-for="(r, i) in (queryResult.steps?.step3?.bm25_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">#{{ i + 1 }} · {{ r.chunk_id }} · {{ (r._score || r.score || 0).toFixed(3) }}</div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.source_zh" class="chunk-source">{{ r.source_zh }}</div>
                          </div>
                        </a-tab-pane>
                        <a-tab-pane key="dense" tab="Dense 原始">
                          <div
                            v-for="(r, i) in (queryResult.steps?.step3?.dense_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">#{{ i + 1 }} · {{ r.chunk_id }} · {{ (r._score || r.score || 0).toFixed(3) }}</div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.source_zh" class="chunk-source">{{ r.source_zh }}</div>
                            <div v-if="r.rewritten_query" class="chunk-rewritten-query">改写Query: "{{ r.rewritten_query }}"</div>
                          </div>
                        </a-tab-pane>
                        <a-tab-pane
                          v-if="(queryResult.steps?.step3?.expanded_results || []).length"
                          key="route3"
                          tab="路3 扩展结果"
                        >
                          <div
                            v-for="(r, i) in (queryResult.steps.step3.expanded_results || [])"
                            :key="r.chunk_id || i"
                            class="chunk-row"
                          >
                            <div class="chunk-meta">
                              #{{ i + 1 }} · expanded_from: {{ r.expanded_from }} · {{ r.chunk_id }} ·
                              {{ (r.score != null ? r.score : r._score || 0).toFixed(3) }}
                            </div>
                            <div class="chunk-text">{{ chunkPreview(r.text) }}</div>
                            <div v-if="r.source_zh" class="chunk-source">{{ r.source_zh }}</div>
                          </div>
                        </a-tab-pane>
                      </a-tabs>
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 4 Prompt">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <div class="prompt-meta">
                        {{ queryResult.steps?.step4?.prompt_type || "—" }} · 约
                        {{ queryResult.steps?.step4?.token_estimate ?? "—" }} tokens
                      </div>
                      <a-textarea
                        :value="queryResult.steps?.step4?.prompt"
                        readonly
                        :rows="12"
                        class="prompt-textarea"
                      />
                    </a-card>
                  </template>
                </a-step>
                <a-step title="Step 5 生成结果">
                  <template #description>
                    <a-card size="small" class="step-card">
                      <template v-if="queryResult.steps?.step5?.skipped"> 已跳过 </template>
                      <template v-else-if="queryResult.answer">
                        <pre class="answer-pre">{{ queryResult.answer }}</pre>
                      </template>
                      <template v-else-if="queryResult.steps?.step5?.error">
                        {{ queryResult.steps.step5.error }}
                      </template>
                      <template v-else> — </template>
                    </a-card>
                  </template>
                  </a-step>
                </a-steps>
              </template>
            </a-col>
          </a-row>
        </a-card>
      </a-tab-pane>

      <!-- Tab 2：图谱浏览器 -->
      <a-tab-pane key="graph" tab="图谱浏览器">
        <a-card class="tab-card">
          <div class="graph-ops">
            <a-radio-group v-model:value="graphMode" button-style="solid" size="middle">
              <a-radio-button value="explore">邻居查询</a-radio-button>
              <a-radio-button value="path">路径查询</a-radio-button>
              <a-radio-button value="stats">图谱统计</a-radio-button>
            </a-radio-group>
          </div>
          <a-divider style="margin: 12px 0" />
          <div v-if="graphMode === 'explore'" class="graph-form">
            <a-input v-model:value="exploreConcept" placeholder="概念名称" class="graph-input" />
            <a-select v-model:value="exploreHops" :options="[1,2,3,4,5].map(h=>({label: h, value: h}))" class="graph-select" />
            <a-button type="primary" :loading="graphLoading" @click="runExplore">查询</a-button>
          </div>
          <div v-if="graphMode === 'path'" class="graph-form">
            <a-input v-model:value="pathConceptA" placeholder="起点概念" class="graph-input graph-input-sm" />
            <a-input v-model:value="pathConceptB" placeholder="终点概念" class="graph-input graph-input-sm" />
            <a-select v-model:value="pathMaxHops" :options="[1,2,3,4,5].map(h=>({label: h, value: h}))" class="graph-select" />
            <a-button type="primary" :loading="graphLoading" @click="runPath">查询</a-button>
          </div>
          <div v-if="graphMode === 'stats'" class="graph-form">
            <a-button type="primary" :loading="graphLoading" @click="runStats">查看统计</a-button>
          </div>
          <div class="graph-result">
          <template v-if="graphMode === 'explore' && exploreResult">
            <a-table
              :columns="neighborTableColumns"
              :data-source="exploreResult.neighbors || []"
              :pagination="false"
              :row-key="(_, index) => `nb-${index}`"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'edge'">
                  <span class="neighbor-edge-text">{{ formatNeighborEdge(record) }}</span>
                </template>
              </template>
            </a-table>
          </template>
          <template v-else-if="graphMode === 'path' && pathResult">
            <p>路径数：{{ pathResult.path_count ?? 0 }}</p>
            <p v-if="pathResult.shortest_path">最短路径：{{ pathSegmentDisplay(pathResult.shortest_path) }}</p>
            <div v-if="(pathResult.paths || []).length">
              <p>所有路径：</p>
              <ul>
                <li v-for="(p, i) in pathResult.paths" :key="i">{{ pathSegmentDisplay(p) }}</li>
              </ul>
            </div>
          </template>
          <template v-else-if="graphMode === 'stats' && statsResult">
            <a-descriptions bordered size="small" :column="1">
              <a-descriptions-item label="Neo4j 可用">{{ statsResult.available ? "是" : "否" }}</a-descriptions-item>
              <a-descriptions-item label="概念数">{{ statsResult.concept_count ?? 0 }}</a-descriptions-item>
              <a-descriptions-item label="关系数">{{ statsResult.relation_count ?? 0 }}</a-descriptions-item>
              <a-descriptions-item label="关系类型分布">
                <span v-for="(cnt, type) in (statsResult.relation_types || {})" :key="type">
                  {{ type }}: {{ cnt }} &nbsp;
                </span>
              </a-descriptions-item>
            </a-descriptions>
          </template>
          </div>
        </a-card>
      </a-tab-pane>

      <!-- Tab 3：单独检索测试 -->
      <a-tab-pane key="search_only" tab="单独检索测试">
        <a-card class="tab-card">
          <div class="search-only-input">
            <a-textarea v-model:value="searchOnlyQuery" placeholder="输入查询问题..." :rows="3" class="query-input" />
            <div class="search-only-options">
              <span class="label">检索模式：</span>
              <a-checkbox-group v-model:value="searchOnlyModes" :options="searchOnlyModeOptions" />
            </div>
            <div v-if="searchOnlyModes.includes('route3')" class="route3-hint">
              <a-input v-model:value="route3Concept" placeholder="输入概念名，用于路3 骨架扩展检索（留空则由查询自动抽取）" allow-clear class="route3-input" />
            </div>
            <div class="search-only-params">
              <span class="label">Top-K</span>
              <a-input-number v-model:value="searchOnlyTopK" :min="1" :max="100" size="small" />
              <span class="label">RRF K</span>
              <a-input-number v-model:value="searchOnlyRrfK" :min="20" :max="100" size="small" />
            </div>
            <a-button type="primary" :loading="searchOnlyLoading" @click="runSearchOnly">执行</a-button>
          </div>
          <div v-if="searchOnlyResult" class="search-only-result">
            <a-row :gutter="16">
              <a-col v-for="col in getSearchOnlyColumns()" :key="col.key" :span="24 / Math.max(1, getSearchOnlyColumns().length)" class="result-col-wrap">
                <a-card :title="`${col.title}（${(col.data || []).length} 条）`" size="small" class="result-col">
                <div
                  v-for="(r, idx) in (col.data || [])"
                  :key="r.chunk_id || idx"
                  class="chunk-row"
                  :class="{ 'chunk-multi-hit': chunkIdSets().includes(r.chunk_id) }"
                >
                  <div class="chunk-meta">#{{ idx + 1 }} · {{ r.chunk_id }} · {{ (r.score != null ? r.score : r._score || 0).toFixed(3) }}</div>
                  <a-collapse>
                    <a-collapse-panel :key="idx">
                      <template #header>
                        <span class="chunk-text-preview">{{ chunkPreview150(r.text) }}</span>
                      </template>
                      <pre class="chunk-full-text">{{ r.text }}</pre>
                    </a-collapse-panel>
                  </a-collapse>
                  <div v-if="r.book_title || r.message_title" class="chunk-meta">
                    {{ r.book_title }} / {{ r.message_title }} / {{ r.section_title }}
                  </div>
                </div>
                </a-card>
              </a-col>
            </a-row>
          </div>
        </a-card>
      </a-tab-pane>

      <!-- Tab 4：Prompt 预览 -->
      <a-tab-pane key="prompt_preview" tab="Prompt 预览">
        <a-card class="tab-card">
          <div class="prompt-preview-input">
            <a-textarea v-model:value="promptPreviewQuery" placeholder="输入查询问题..." :rows="3" class="query-input" />
            <p class="hint">参数与 Tab 1 共用，可在 Tab 1 的「检索参数」中调整。</p>
            <a-button type="primary" :loading="promptPreviewLoading" @click="runPromptPreview">生成 Prompt</a-button>
          </div>
          <div v-if="promptPreviewResult" class="prompt-preview-result">
            <div class="prompt-meta-row">
              <a-tag :color="promptPreviewResult.steps?.step4?.prompt_type === 'skeleton' ? 'blue' : 'default'">
                {{ promptPreviewResult.steps?.step4?.prompt_type === "skeleton" ? "骨架式 Prompt" : "平铺式 Prompt" }}
              </a-tag>
              <span class="prompt-token-hint">约 {{ promptPreviewResult.steps?.step4?.token_estimate ?? "—" }} tokens</span>
            </div>
            <a-textarea :value="promptPreviewResult.steps?.step4?.prompt" readonly :rows="16" class="prompt-full-textarea" />
            <a-collapse class="steps-summary" :bordered="false">
            <a-collapse-panel key="step1" header="Step 1 概念抽取">
              <a-tag v-for="c in (promptPreviewResult.steps?.step1?.concepts || [])" :key="c">{{ c }}</a-tag>
            </a-collapse-panel>
            <a-collapse-panel key="step1_5" header="Step 1.5 概念规范化">
              <span>命中：</span>
              <a-tag v-for="n in (promptPreviewResult.steps?.step1_5?.normalized || [])" :key="n" color="green">{{ n }}</a-tag>
              <span style="margin-left: 8px">丢弃：</span>
              <a-tag v-for="d in (promptPreviewResult.steps?.step1_5?.dropped || [])" :key="d" color="red">{{ d }}</a-tag>
            </a-collapse-panel>
            <a-collapse-panel key="step2" header="Step 2 概念骨架">
              <template v-if="promptPreviewResult.steps?.step2?.skeleton">
                <pre class="skeleton-pre">{{ formatSkeleton(promptPreviewResult.steps.step2.skeleton) }}</pre>
              </template>
              <template v-else>无骨架</template>
            </a-collapse-panel>
            <a-collapse-panel key="step3" header="Step 3 检索统计">
              主检索 {{ (promptPreviewResult.steps?.step3?.main_results || []).length }} 条，
              扩展 {{ (promptPreviewResult.steps?.step3?.expanded_results || []).length }} 条
            </a-collapse-panel>
            </a-collapse>
          </div>
        </a-card>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<style scoped lang="less">
/* 页面标题区：与 ToolsHeader 风格一致，标题 + 健康指示器一行 */
.kg-rag-header {
  padding: 10px 20px;
  display: flex;
  align-items: center;
  font-size: large;
  font-weight: bold;
  color: #55bbff;
  background-color: #001529;
  margin-bottom: 16px;
  gap: 12px;
  .header-left {
    cursor: pointer;
    display: flex;
    align-items: center;
    &:hover .header-back {
      color: #1677ff;
      transform: scale(1.1);
      transition: 0.2s;
    }
  }
  .header-title {
    flex: 1;
    text-align: center;
  }
  .header-health {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    font-weight: normal;
    color: rgba(255, 255, 255, 0.85);
    .health-item {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .health-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #ff4d4f;
      flex-shrink: 0;
      &.ok {
        background: #52c41a;
      }
    }
    .health-text {
      color: rgba(255, 255, 255, 0.65);
    }
    .health-refresh {
      color: #55bbff;
      padding: 0 4px;
    }
  }
}

.kg-rag-page {
  padding: 1em;
  max-width: 1400px;
  margin: 0 auto;
}

.main-tabs {
  :deep(.ant-tabs-content) {
    padding-top: 12px;
  }
}

.tab-card {
  margin-bottom: 16px;
}

/* Tab 1 全流程查询 */
.query-section {
  margin-bottom: 16px;
}
.query-input {
  margin-bottom: 16px;
}
.param-collapse {
  margin-bottom: 16px;
  :deep(.ant-collapse-header) {
    align-items: center;
  }
}
.param-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
  .param-label {
    min-width: 88px;
    font-size: 13px;
    color: #333;
    flex-shrink: 0;
  }
  .param-control {
    flex: 1;
    min-width: 0;
  }
  .param-select {
    width: 100%;
  }
  &.param-checkboxes {
    padding-top: 4px;
    .param-label {
      min-width: 0;
    }
  }
}
.query-btn {
  width: 100%;
  margin-top: 0;
}

.result-placeholder {
  color: #999;
  padding: 32px 24px;
  text-align: center;
  background: #fafafa;
  border-radius: 8px;
}

.result-steps {
  :deep(.ant-steps-item-description) {
    padding-bottom: 20px;
  }
  :deep(.ant-steps-item) {
    .ant-steps-item-container {
      .ant-steps-item-content {
        .ant-steps-item-title {
          font-weight: 500;
        }
      }
    }
  }
}

.step-card {
  margin-top: 12px;
  margin-bottom: 4px;
  :deep(.ant-card-body) {
    padding: 12px;
  }
  .raw-pre,
  .skeleton-pre,
  .answer-pre {
    white-space: pre-wrap;
    word-break: break-all;
    font-size: 12px;
    max-height: 200px;
    overflow: auto;
    margin: 0;
    color: #333;
  }
  .prompt-meta {
    margin-bottom: 8px;
    font-size: 13px;
    color: #666;
  }
  .prompt-textarea {
    font-family: monospace;
    font-size: 12px;
  }
  .chunk-row {
    margin-bottom: 10px;
    padding: 10px 12px;
    background: #f5f5f5;
    border-radius: 6px;
    &:last-child {
      margin-bottom: 0;
    }
    .chunk-meta {
      font-size: 12px;
      color: #8c8c8c;
      margin-bottom: 4px;
      line-height: 1.4;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 4px;
    }
    .source-route-tag {
      font-size: 11px;
      line-height: 1.2;
      padding: 0 4px;
      margin: 0;
    }
    .chunk-text {
      font-size: 13px;
      color: #333;
      line-height: 1.5;
      margin-bottom: 2px;
    }
    .chunk-source {
      font-size: 11px;
      color: #999;
      margin-top: 2px;
      line-height: 1.4;
    }
    .chunk-rewritten-query {
      font-size: 11px;
      color: #bbb;
      margin-top: 2px;
      line-height: 1.4;
    }
  }
}

/* Tab 2 图谱浏览器 */
.graph-ops {
  margin-bottom: 12px;
}
.graph-form {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  .graph-input {
    width: 200px;
  }
  .graph-input-sm {
    width: 140px;
  }
  .graph-select {
    width: 80px;
  }
}
.graph-result {
  min-height: 120px;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  margin-top: 16px;
  :deep(.ant-table) {
    font-size: 13px;
  }
  :deep(.ant-descriptions-item-label) {
    font-weight: 500;
    color: #333;
  }
  p, ul {
    margin-bottom: 8px;
    font-size: 13px;
    color: #333;
  }
}

/* Tab 3 单独检索测试 */
.search-only-input {
  margin-bottom: 16px;
  .search-only-options {
    margin: 12px 0;
    .label {
      margin-right: 8px;
      font-weight: 500;
      font-size: 13px;
    }
    :deep(.ant-checkbox-group) {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 16px;
    }
  }
  .route3-hint {
    margin: 12px 0;
    .route3-input {
      max-width: 400px;
    }
  }
  .search-only-params {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 12px 0;
    .label {
      font-weight: 500;
      font-size: 13px;
    }
  }
}

.search-only-result {
  margin-top: 16px;
  .result-col-wrap {
    min-width: 0;
  }
  .result-col {
    height: 100%;
    :deep(.ant-card-head) {
      min-height: 40px;
      padding: 0 12px;
      font-size: 13px;
    }
    :deep(.ant-card-body) {
      padding: 12px;
      max-height: 60vh;
      overflow-y: auto;
    }
  }
  .chunk-row {
    margin-bottom: 10px;
    padding: 8px 10px;
    background: #fafafa;
    border-radius: 6px;
    &.chunk-multi-hit {
      background: #f0f7ff;
      border: 1px solid #bae7ff;
    }
    .chunk-meta {
      font-size: 12px;
      color: #8c8c8c;
      margin-bottom: 4px;
    }
    .chunk-text-preview {
      font-size: 13px;
      color: #333;
    }
    .chunk-full-text {
      white-space: pre-wrap;
      word-break: break-all;
      font-size: 12px;
      max-height: 180px;
      overflow: auto;
      margin: 0;
      color: #333;
    }
  }
}

/* Tab 4 Prompt 预览 */
.prompt-preview-input {
  margin-bottom: 16px;
  .hint {
    color: #666;
    font-size: 12px;
    margin: 8px 0 12px;
  }
}

.prompt-preview-result {
  margin-top: 16px;
  .prompt-meta-row {
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .prompt-token-hint {
    font-size: 13px;
    color: #666;
  }
  .prompt-full-textarea {
    font-family: monospace;
    font-size: 12px;
    margin-bottom: 16px;
    resize: none;
  }
  .steps-summary {
    :deep(.ant-collapse-item) {
      .ant-collapse-header {
        padding: 8px 0;
        font-size: 13px;
      }
      .ant-collapse-content-box {
        padding: 8px 0 12px;
      }
    }
    .skeleton-pre {
      white-space: pre-wrap;
      word-break: break-all;
      font-size: 12px;
      max-height: 120px;
      overflow: auto;
      margin: 0;
      color: #333;
    }
  }
}
</style>
