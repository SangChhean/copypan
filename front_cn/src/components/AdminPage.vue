<template>
  <div class="admin-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="router.push('/')">‹‹ 返回</button>
      <span class="cn-page-title">管理后台</span>
    </div>

    <div class="cn-content-wrap">
      <div class="cn-content-card cn-content-card--wide">
      <div class="admin-content">

        <section class="admin-section">
          <div class="admin-section-title">管理统计</div>
          <div class="admin-token-row">
            <a-button type="primary" :loading="statsLoading" @click="loadStats">
              刷新数据
            </a-button>
          </div>
          <div v-if="apiError" class="admin-error">{{ apiError }}</div>
        </section>

        <section class="admin-section">
          <div class="admin-guide-section">
            <div class="admin-mat-title">使用说明 PDF</div>
            <a-upload
              :show-upload-list="false"
              :before-upload="beforeGuideUpload"
              :custom-request="customGuideUpload"
            >
              <a-button type="primary">上传 / 替换使用说明 PDF</a-button>
            </a-upload>
          </div>
        </section>

        <section v-if="stats" class="admin-section">
          <a-tabs v-model:activeKey="activeTab" class="cn-admin-tabs">
            <a-tab-pane key="stats" tab="统计">
              <div class="admin-stat-grid">
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ stats.total_requests }}</div>
                  <div class="admin-stat-label">总请求数</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ pct(stats.cache_hit_rate) }}</div>
                  <div class="admin-stat-label">缓存命中率</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ pct(stats.found_rate_new) }}</div>
                  <div class="admin-stat-label">找到率（非缓存）</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">${{ stats.total_cost_usd }}</div>
                  <div class="admin-stat-label">累计费用</div>
                </div>
                <div class="admin-stat-card">
                  <div class="admin-stat-value">{{ stats.avg_elapsed_ms }}ms</div>
                  <div class="admin-stat-label">平均耗时</div>
                </div>
              </div>

              <div v-if="stats.step_fail_records && stats.step_fail_records.length" class="admin-fail-wrap">
                <div class="admin-section-title">
                  未找到记录
                  <span class="admin-section-sub">（最近 {{ stats.step_fail_records.length }} 条）</span>
                </div>
                <div class="admin-fail-list">
                  <div
                    v-for="(rec, idx) in stats.step_fail_records"
                    :key="idx"
                    class="admin-fail-item"
                  >
                    <div class="admin-fail-question">{{ rec.question }}</div>
                    <div class="admin-fail-meta">
                      <span>{{ rec.ts }}</span>
                      <span>{{ rec.total_elapsed_ms }}ms</span>
                      <span>${{ rec.total_cost_usd }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="admin-feedback-wrap">
                <div class="admin-section-title">答案反馈汇总</div>
                <div v-if="feedbackStats" class="admin-feedback-grid">
                  <div class="admin-stat-card">
                    <div class="admin-stat-value">{{ feedbackStats.thumbs_up || 0 }}</div>
                    <div class="admin-stat-label">👍 总数</div>
                  </div>
                  <div class="admin-stat-card">
                    <div class="admin-stat-value">{{ feedbackStats.thumbs_down || 0 }}</div>
                    <div class="admin-stat-label">👎 总数</div>
                  </div>
                  <div class="admin-stat-card">
                    <div class="admin-stat-value">{{ pct(feedbackStats.rate || 0) }}</div>
                    <div class="admin-stat-label">好评率</div>
                  </div>
                </div>
                <div v-if="feedbackStats && feedbackStats.recent_down && feedbackStats.recent_down.length" class="admin-feedback-list">
                  <div
                    v-for="(rec, idx) in feedbackStats.recent_down"
                    :key="idx"
                    class="admin-feedback-item"
                  >
                    <div class="admin-feedback-head">
                      <span>{{ rec.created_at || '-' }}</span>
                      <span>{{ rec.username || '-' }}</span>
                    </div>
                    <div class="admin-feedback-text"><b>问：</b>{{ truncateText(rec.question, 50) }}</div>
                    <div class="admin-feedback-text"><b>答：</b>{{ truncateText(rec.answer, 100) }}</div>
                  </div>
                </div>
                <div v-else-if="feedbackStats" class="admin-feedback-empty">暂无反馈数据</div>
              </div>
            </a-tab-pane>

            <a-tab-pane key="cache" tab="缓存">
              <div class="admin-cache-row">
                <span class="admin-cache-desc">清除所有 <code>cn:cache:*</code> 缓存</span>
                <div class="admin-cache-actions">
                  <a-popconfirm
                    title="确认清除所有问答缓存？"
                    ok-text="确认"
                    cancel-text="取消"
                    @confirm="clearCache"
                  >
                    <a-button danger :loading="clearLoading">清除缓存</a-button>
                  </a-popconfirm>
                  <a-button danger ghost :loading="clearStatsLoading" @click="clearStats">
                    清空统计
                  </a-button>
                </div>
              </div>
              <div v-if="clearResult" class="admin-clear-result">
                已删除 {{ clearResult.deleted }} 条缓存（前缀：{{ clearResult.prefix }}）
              </div>
            </a-tab-pane>

            <a-tab-pane key="debug" tab="调试">
              <DebugPanel embedded />
            </a-tab-pane>

            <a-tab-pane key="invites" tab="邀请码">
              <div class="admin-invite-create">
                <a-input
                  v-model:value="inviteCode"
                  placeholder="输入邀请码（留空可自动生成）"
                  class="admin-invite-input"
                  @pressEnter="createInvite"
                />
                <a-button type="primary" :loading="inviteLoading" @click="createInvite">
                  生成邀请码
                </a-button>
              </div>

              <div class="admin-table-wrap">
                <table class="admin-table cn-admin-table">
                  <thead>
                    <tr>
                      <th>邀请码</th>
                      <th>状态</th>
                      <th>使用者</th>
                      <th>创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="invitesLoading">
                      <td colspan="4" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!invites.length">
                      <td colspan="4" class="admin-table-empty">暂无邀请码</td>
                    </tr>
                    <tr v-else v-for="row in invites" :key="row.id">
                      <td>{{ row.code }}</td>
                      <td>
                        <span :class="row.used ? 'tag-fail' : 'tag-ok'">
                          {{ row.used ? '已使用' : '未使用' }}
                        </span>
                      </td>
                      <td>{{ row.used_by || '-' }}</td>
                      <td>{{ row.created_at || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="limits" tab="限额设置">
              <div class="admin-table-wrap">
                <table class="admin-table cn-admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>管理员</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="usersLoading">
                      <td colspan="3" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!users.length">
                      <td colspan="3" class="admin-table-empty">暂无用户</td>
                    </tr>
                    <tr v-else v-for="row in users" :key="'lim-' + row.id">
                      <td>{{ row.username }}</td>
                      <td>{{ row.is_admin ? '是' : '否' }}</td>
                      <td>
                        <a-button size="small" @click="openLimitModal(row.username)">
                          设置限额
                        </a-button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>

            <a-tab-pane key="materials" tab="资料管理">
              <a-tabs v-model:activeKey="matTypeTab" class="cn-admin-tabs" style="margin-bottom:16px">
                <a-tab-pane key="conference" tab="节期相关" />
                <a-tab-pane key="service" tab="事奉类" />
                <a-tab-pane key="community" tab="社区排" />
                <a-tab-pane key="sisters" tab="姊妹" />
                <a-tab-pane key="young_pro" tab="青职" />
                <a-tab-pane key="college" tab="大专" />
                <a-tab-pane key="youth" tab="青少年" />
                <a-tab-pane key="kids" tab="儿童" />
              </a-tabs>
              <a-card title="分类管理" size="small" class="admin-mat-card">
                <div class="admin-mat-create">
                  <a-input v-model:value="newCatName" placeholder="分类名称" class="admin-mat-input" />
                  <a-select
                    v-model:value="newCatParentId"
                    placeholder="父分类（留空为根分类）"
                    :options="[{ label: '（根分类）', value: null }, ...flatMatOptions]"
                    allow-clear
                    style="min-width:200px"
                  />
                  <a-button type="primary" :loading="catCreating" @click="createCategory">新建</a-button>
                </div>
                <div class="admin-mat-tree">
                  <table class="admin-cat-table">
                    <thead>
                      <tr>
                        <th>分类名</th>
                        <th>目录名</th>
                        <th>创建时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <AdminCatRow
                        v-for="node in matCategories"
                        :key="node.id"
                        :node="node"
                        :depth="0"
                        :renaming-id="renamingCatId"
                        :rename-value="renameCatName"
                        @start-rename="startRename"
                        @save-rename="saveRename"
                        @cancel-rename="cancelRename"
                        @update-rename="renameCatName = $event"
                        @delete="deleteCategory"
                      />
                      <tr v-if="!matCategories.length && !matCategoriesLoading">
                        <td colspan="4" class="admin-mat-empty">暂无分类</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </a-card>

              <a-card title="文件管理" size="small" class="admin-mat-card">
                <div class="admin-mat-toolbar">
                  <span>分类：</span>
                  <a-select
                    v-model:value="matSelectedCategoryId"
                    placeholder="不选（按文件夹路径自动建分类）"
                    style="min-width:520px"
                    :options="[{ label: '── 不选（批量上传自动建分类）──', value: null }, ...flatMatOptions]"
                    :allow-clear="true"
                    @change="onMatCategoryChange"
                  />
                </div>
                <div class="admin-mat-file-toolbar">
                  <div class="admin-mat-file-toolbar-left">
                    <a-upload
                      :show-upload-list="false"
                      :before-upload="beforeMatUpload"
                      :custom-request="customMatUpload"
                    >
                      <a-button type="primary" :disabled="!matSelectedCategoryId">上传文件</a-button>
                    </a-upload>
                    <input
                      ref="folderInputRef"
                      type="file"
                      webkitdirectory
                      multiple
                      style="display:none"
                      @change="onFolderSelected"
                    />
                    <a-button type="primary" :loading="batchUploading" @click="folderInputRef.click()">
                      批量上传
                    </a-button>
                    <span v-if="batchResult" class="admin-mat-batch-result">
                      已上传 {{ batchResult.uploaded }} 个文件
                      <span v-if="batchResult.errors?.length" class="admin-mat-batch-errors">
                        ，{{ batchResult.errors.length }} 个失败
                      </span>
                    </span>
                  </div>
                  <div class="admin-mat-file-toolbar-action">
                    <a-popconfirm
                      title="确认删除该分类下所有文件？此操作不可恢复。"
                      ok-text="确认删除"
                      cancel-text="取消"
                      ok-type="danger"
                      @confirm="deleteAllFiles"
                    >
                      <a-button
                        danger
                        size="small"
                        :disabled="!matSelectedCategoryId || matFiles.length === 0"
                      >
                        删除全部
                      </a-button>
                    </a-popconfirm>
                  </div>
                </div>
                <a-table
                  :columns="matFileColumns"
                  :data-source="matFiles"
                  :loading="matFilesLoading"
                  row-key="id"
                  size="small"
                  :pagination="false"
                  class="admin-mat-file-table"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'size_bytes'">
                      {{ formatMatSize(record.size_bytes) }}
                    </template>
                    <template v-else-if="column.key === 'created_at'">
                      {{ formatMatDate(record.created_at) }}
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-popconfirm title="确认删除该文件？" @confirm="deleteMaterial(record.id)">
                        <a-button danger size="small">删除</a-button>
                      </a-popconfirm>
                    </template>
                  </template>
                </a-table>
              </a-card>
            </a-tab-pane>

            <a-tab-pane key="users" tab="用户">
              <div class="admin-table-wrap">
                <table class="admin-table cn-admin-table">
                  <thead>
                    <tr>
                      <th>用户名</th>
                      <th>管理员</th>
                      <th>创建时间</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="usersLoading">
                      <td colspan="4" class="admin-table-empty">加载中...</td>
                    </tr>
                    <tr v-else-if="!users.length">
                      <td colspan="4" class="admin-table-empty">暂无用户</td>
                    </tr>
                    <tr v-else v-for="row in users" :key="row.id">
                      <td>{{ row.username }}</td>
                      <td>{{ row.is_admin ? '是' : '否' }}</td>
                      <td>{{ row.created_at || '-' }}</td>
                      <td>
                        <a-button size="small" class="admin-user-limit-btn" @click="openLimitModal(row.username)">
                          设置限额
                        </a-button>
                        <a-button size="small" class="admin-user-limit-btn" @click="openResetPwdModal(row.username)">
                          重置密码
                        </a-button>
                        <a-button
                          v-if="row.username !== currentUsername"
                          size="small"
                          class="admin-user-limit-btn"
                          :style="row.is_admin ? 'border-color:#E24B4A;color:#E24B4A' : 'border-color:#C9A96E;color:#C9A96E'"
                          @click="toggleAdmin(row.username, row.is_admin)"
                        >
                          {{ row.is_admin ? '取消管理员' : '设为管理员' }}
                        </a-button>
                        <a-popconfirm
                          v-if="row.username !== currentUsername"
                          title="确认删除该用户？"
                          ok-text="确认"
                          cancel-text="取消"
                          @confirm="deleteUser(row.username)"
                        >
                          <a-button danger size="small" :loading="deletingUser === row.username">删除</a-button>
                        </a-popconfirm>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </a-tab-pane>
          </a-tabs>
        </section>

      </div>
      </div>
    </div>

    <a-modal
      v-model:open="limitModalOpen"
      :title="limitModalUser ? `${limitModalUser} 的每日限额` : '每日限额'"
      ok-text="批量保存"
      cancel-text="取消"
      :confirm-loading="limitSaving"
      @ok="saveAllLimits"
    >
      <div v-if="limitModalLoading" class="admin-limit-loading">加载中...</div>
      <div v-else class="admin-limit-form">
        <div v-for="item in limitFields" :key="item.key" class="admin-limit-row">
          <div class="admin-limit-label">
            {{ item.label }}
            <span v-if="item.hint" class="admin-limit-hint">（{{ item.hint }}）</span>
          </div>
          <div class="admin-limit-usage" v-if="limitUsage[item.key]">
            今日已用 {{ limitUsage[item.key].used ?? 0 }} / {{ limitUsage[item.key].limit ?? 0 }}
          </div>
          <a-input-number v-model:value="limitValues[item.key]" :min="-1" style="width: 120px" />
          <div v-if="limitValues[item.key] === -1" class="admin-limit-note">-1 = 不限次数</div>
        </div>
      </div>
    </a-modal>

    <a-modal
      v-model:open="resetPwdModalOpen"
      :title="`重置 ${resetPwdUser} 的密码`"
      ok-text="确认重置"
      cancel-text="取消"
      :confirm-loading="resetPwdSaving"
      @ok="saveResetPwd"
    >
      <a-input-password
        v-model:value="resetPwdValue"
        placeholder="请输入新密码（不少于6位）"
        @pressEnter="saveResetPwd"
      />
    </a-modal>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import { getUsername } from '@/utils/auth.js'
import DebugPanel from '@/components/DebugPanel.vue'

const AdminCatNode = defineComponent({
  name: 'AdminCatNode',
  props: {
    node: { type: Object, required: true },
    renamingId: { type: Number, default: null },
    renameValue: { type: String, default: '' },
    depth: { type: Number, default: 0 },
  },
  emits: ['start-rename', 'save-rename', 'cancel-rename', 'update-rename', 'delete'],
  setup(props, { emit }) {
    const open = ref(true)
    return () => {
      const node = props.node
      const indent = props.depth * 16
      const isRenaming = props.renamingId === node.id
      const hasChildren = node.children && node.children.length > 0

      const rowContent = isRenaming
        ? [
            h('input', {
              value: props.renameValue,
              class: 'admin-rename-input',
              onInput: (e) => emit('update-rename', e.target.value),
              onKeydown: (e) => {
                if (e.key === 'Enter') emit('save-rename', node.id)
                if (e.key === 'Escape') emit('cancel-rename')
              },
            }),
            h('button', {
              class: 'admin-rename-btn admin-rename-btn--ok',
              onClick: () => emit('save-rename', node.id),
            }, '✓'),
            h('button', {
              class: 'admin-rename-btn',
              onClick: () => emit('cancel-rename'),
            }, '✕'),
          ]
        : [
            h('span', { class: 'admin-cat-name' }, [
              hasChildren
                ? h('span', {
                    class: ['admin-cat-arrow', open.value && 'admin-cat-arrow--open'],
                    onClick: () => { open.value = !open.value },
                  }, '▶ ')
                : h('span', { style: 'margin-right:14px' }, ''),
              node.name,
            ]),
            h('div', { class: 'admin-cat-actions' }, [
              h('button', {
                class: 'admin-cat-btn',
                onClick: () => emit('start-rename', node),
              }, '改名'),
              h('button', {
                class: 'admin-cat-btn admin-cat-btn--danger',
                onClick: () => emit('delete', node),
              }, '删除'),
            ]),
          ]

      const children = hasChildren && open.value
        ? h('div', {},
            node.children.map((child) =>
              h(AdminCatNode, {
                key: child.id,
                node: child,
                renamingId: props.renamingId,
                renameValue: props.renameValue,
                depth: props.depth + 1,
                onStartRename: (n) => emit('start-rename', n),
                onSaveRename: (id) => emit('save-rename', id),
                onCancelRename: () => emit('cancel-rename'),
                onUpdateRename: (v) => emit('update-rename', v),
                onDelete: (n) => emit('delete', n),
              })
            )
          )
        : null

      return h('div', { style: { paddingLeft: `${indent}px` } }, [
        h('div', { class: 'admin-mat-tree-node' }, rowContent),
        children,
      ])
    }
  },
})

const AdminCatRow = defineComponent({
  name: 'AdminCatRow',
  props: {
    node: { type: Object, required: true },
    depth: { type: Number, default: 0 },
    renamingId: { type: Number, default: null },
    renameValue: { type: String, default: '' },
  },
  emits: ['start-rename', 'save-rename', 'cancel-rename', 'update-rename', 'delete'],
  setup(props, { emit }) {
    const open = ref(true)
    return () => {
      const node = props.node
      const hasChildren = node.children && node.children.length > 0
      const isRenaming = props.renamingId === node.id
      const indent = props.depth * 16

      const nameCell = isRenaming
        ? h('td', [
            h('input', {
              value: props.renameValue,
              class: 'admin-rename-input',
              onInput: (e) => emit('update-rename', e.target.value),
              onKeydown: (e) => {
                if (e.key === 'Enter') emit('save-rename', node.id)
                if (e.key === 'Escape') emit('cancel-rename')
              },
            }),
            h('button', {
              class: 'admin-rename-btn admin-rename-btn--ok',
              onClick: () => emit('save-rename', node.id),
            }, '✓'),
            h('button', {
              class: 'admin-rename-btn',
              onClick: () => emit('cancel-rename'),
            }, '✕'),
          ])
        : h('td', [
            h('span', { style: { paddingLeft: `${indent}px` } }, [
              hasChildren
                ? h('span', {
                    style: {
                      cursor: 'pointer',
                      marginRight: '4px',
                      fontSize: '10px',
                      display: 'inline-block',
                      transform: open.value ? 'rotate(90deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s',
                    },
                    onClick: () => { open.value = !open.value },
                  }, '▶')
                : h('span', { style: { marginRight: '14px' } }, ''),
            ]),
            node.name,
          ])

      const dirCell = h('td', { class: 'admin-cat-dir' }, node.dir_name || '-')

      const dateCell = h('td', { class: 'admin-cat-meta' },
        node.created_at
          ? new Date(node.created_at).toLocaleString('zh-CN', { hour12: false }).slice(0, 10)
          : '-'
      )

      const actionCell = h('td', [
        h('button', {
          class: 'admin-cat-btn',
          onClick: () => emit('start-rename', node),
        }, '改名'),
        h('button', {
          class: 'admin-cat-btn admin-cat-btn--danger',
          onClick: () => emit('delete', node),
        }, '删除'),
      ])

      const rows = [h('tr', { class: 'admin-cat-tr' }, [nameCell, dirCell, dateCell, actionCell])]

      if (hasChildren && open.value) {
        node.children.forEach((child) => {
          rows.push(h(AdminCatRow, {
            key: child.id,
            node: child,
            depth: props.depth + 1,
            renamingId: props.renamingId,
            renameValue: props.renameValue,
            onStartRename: (n) => emit('start-rename', n),
            onSaveRename: (id) => emit('save-rename', id),
            onCancelRename: () => emit('cancel-rename'),
            onUpdateRename: (v) => emit('update-rename', v),
            onDelete: (n) => emit('delete', n),
          }))
        })
      }

      return rows
    }
  },
})

const router = useRouter()
const stats = ref(null)
const statsLoading = ref(false)
const clearLoading = ref(false)
const clearStatsLoading = ref(false)
const apiError = ref('')
const clearResult = ref(null)
const feedbackStats = ref(null)
const activeTab = ref('stats')
const inviteCode = ref('')
const invites = ref([])
const users = ref([])
const inviteLoading = ref(false)
const invitesLoading = ref(false)
const usersLoading = ref(false)
const deletingUser = ref('')

const currentUsername = computed(() => getUsername())

const resetPwdModalOpen = ref(false)
const resetPwdUser = ref('')
const resetPwdValue = ref('')
const resetPwdSaving = ref(false)

const limitModalOpen = ref(false)
const limitModalUser = ref('')
const limitModalLoading = ref(false)
const limitSaving = ref(false)
const limitValues = ref({ outline: 3, translate: 3, qa: 3, burden: 20, asr: 20, roundtable: 2 })
const limitUsage = ref({})

const limitFields = [
  { key: 'outline', label: '纲目制作' },
  { key: 'translate', label: '纲目翻译' },
  { key: 'qa', label: '职事问答' },
  { key: 'burden', label: '负担说明', hint: '防滥用护栏' },
  { key: 'asr', label: '语音转写', hint: '防滥用护栏' },
  { key: 'roundtable', label: '小排材料制作' },
]

const matCategories = ref([])
const matTypeTab = ref('conference')
const matCategoriesLoading = ref(false)
const matFiles = ref([])
const matFilesLoading = ref(false)
const matSelectedCategoryId = ref(null)
const newCatName = ref('')
const catCreating = ref(false)
const newCatParentId = ref(null)
const renamingCatId = ref(null)
const renameCatName = ref('')
const folderInputRef = ref(null)
const batchUploading = ref(false)
const batchResult = ref(null)

const matFileColumns = [
  { title: '文件名', dataIndex: 'display_name', key: 'display_name' },
  { title: '大小', key: 'size_bytes', width: 90 },
  { title: '上传时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 80, align: 'center' },
]

function flattenCategories(nodes, prefix = '') {
  const result = []
  for (const n of nodes) {
    const label = prefix ? `${prefix} / ${n.name}` : n.name
    result.push({ label, value: n.id })
    if (n.children?.length) result.push(...flattenCategories(n.children, label))
  }
  return result
}
const flatMatOptions = computed(() => flattenCategories(matCategories.value))

const MAX_MAT_MB = 200

function pct(val) {
  if (val == null) return '-'
  return (val * 100).toFixed(1) + '%'
}

async function loadStats() {
  statsLoading.value = true
  apiError.value = ''
  clearResult.value = null
  try {
    const res = await http.get('/api/qa/stats')
    stats.value = res.data
    await Promise.all([loadInvites(), loadUsers(), loadFeedbackStats()])
  } catch (e) {
    const status = e.response?.status
    if (status === 403) apiError.value = '需要管理员权限'
    else if (status === 503) apiError.value = '服务不可用（Redis 未连接）'
    else apiError.value = `请求失败（${status || '网络错误'}）`
    stats.value = null
    feedbackStats.value = null
  } finally {
    statsLoading.value = false
  }
}

async function loadInvites() {
  invitesLoading.value = true
  try {
    const res = await http.get('/api/cn/auth/invites')
    invites.value = res.data?.items || []
  } catch (e) {
    const status = e.response?.status
    apiError.value = `邀请码列表加载失败（${status || '网络错误'}）`
  } finally {
    invitesLoading.value = false
  }
}

async function loadUsers() {
  usersLoading.value = true
  try {
    const res = await http.get('/api/cn/auth/users')
    users.value = res.data?.items || []
  } catch (e) {
    const status = e.response?.status
    apiError.value = `用户列表加载失败（${status || '网络错误'}）`
  } finally {
    usersLoading.value = false
  }
}

async function deleteUser(username) {
  if (!username) return
  if (username === getUsername()) {
    message.warning('不能删除自己的账号')
    return
  }
  deletingUser.value = username
  apiError.value = ''
  try {
    await http.delete(`/api/cn/auth/users/${encodeURIComponent(username)}`)
    await loadUsers()
  } catch (e) {
    const status = e.response?.status
    apiError.value = `删除用户失败（${status || '网络错误'}）`
  } finally {
    deletingUser.value = ''
  }
}

function _randomCode() {
  return `INVITE-${Date.now().toString(36).toUpperCase()}`
}

async function createInvite() {
  inviteLoading.value = true
  apiError.value = ''
  try {
    const code = inviteCode.value.trim() || _randomCode()
    await http.post('/api/cn/auth/invite', { code })
    inviteCode.value = ''
    await loadInvites()
  } catch (e) {
    const status = e.response?.status
    apiError.value = `生成邀请码失败（${status || '网络错误'}）`
  } finally {
    inviteLoading.value = false
  }
}

async function clearCache() {
  clearLoading.value = true
  clearResult.value = null
  try {
    const res = await http.post('/api/qa/cache/clear', {})
    const cleared = res.data
    await loadStats()
    clearResult.value = cleared
  } catch (e) {
    apiError.value = `清除失败（${e.response?.status || '网络错误'}）`
  } finally {
    clearLoading.value = false
  }
}

async function clearStats() {
  if (!window.confirm('确认清空统计数据？')) return
  clearStatsLoading.value = true
  apiError.value = ''
  try {
    await http.post('/api/qa/stats/clear', {})
    window.alert('统计数据已清空')
    await loadStats()
  } catch (e) {
    apiError.value = `清空统计失败（${e.response?.status || '网络错误'}）`
  } finally {
    clearStatsLoading.value = false
  }
}

async function loadFeedbackStats() {
  try {
    const res = await http.get('/api/qa/feedback/stats')
    feedbackStats.value = res.data || null
  } catch (e) {
    console.error('load feedback stats failed', e)
    feedbackStats.value = null
  }
}

function truncateText(text, maxLen) {
  const s = (text || '').trim()
  if (!s) return '-'
  return s.length > maxLen ? `${s.slice(0, maxLen)}...` : s
}

async function openLimitModal(username) {
  limitModalUser.value = username
  limitModalOpen.value = true
  limitModalLoading.value = true
  try {
    const res = await http.get(`/api/cn/auth/users/${encodeURIComponent(username)}/limits`)
    const data = res.data || {}
    limitValues.value = { ...data.limits }
    limitUsage.value = { ...data.usage }
  } catch (e) {
    message.error(`加载限额失败（${e.response?.data?.detail || e.response?.status || '网络错误'}）`)
    limitModalOpen.value = false
  } finally {
    limitModalLoading.value = false
  }
}

async function saveAllLimits() {
  if (!limitModalUser.value) return
  limitSaving.value = true
  try {
    for (const item of limitFields) {
      await http.post(`/api/cn/auth/users/${encodeURIComponent(limitModalUser.value)}/limit`, {
        feature: item.key,
        daily_limit: limitValues.value[item.key],
      })
    }
    message.success('已更新')
    limitModalOpen.value = false
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    limitSaving.value = false
  }
}

function openResetPwdModal(username) {
  resetPwdUser.value = username
  resetPwdValue.value = ''
  resetPwdModalOpen.value = true
}

async function saveResetPwd() {
  if (!resetPwdValue.value || resetPwdValue.value.length < 6) {
    message.warning('新密码不能少于6位')
    return
  }
  resetPwdSaving.value = true
  try {
    await http.post(`/api/cn/auth/users/${encodeURIComponent(resetPwdUser.value)}/reset_password`, {
      new_password: resetPwdValue.value,
    })
    message.success('密码已重置')
    resetPwdModalOpen.value = false
  } catch (e) {
    message.error(e?.response?.data?.detail || '重置失败')
  } finally {
    resetPwdSaving.value = false
  }
}

async function toggleAdmin(username, currentIsAdmin) {
  const currentUser = getUsername()
  if (username === currentUser && currentIsAdmin) {
    message.warning('不能取消自己的管理员权限')
    return
  }
  try {
    await http.post(`/api/cn/auth/users/${encodeURIComponent(username)}/admin`, {
      is_admin: !currentIsAdmin,
    })
    message.success(currentIsAdmin ? '已取消管理员' : '已设为管理员')
    await loadUsers()
  } catch (e) {
    message.error(e?.response?.data?.detail || '操作失败')
  }
}

function formatMatSize(bytes) {
  const n = Number(bytes) || 0
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${n} B`
}

function formatMatDate(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

async function loadMatCategories() {
  matCategoriesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials/categories', {
      params: { type: matTypeTab.value },
    })
    matCategories.value = res.data || []
    if (matCategories.value.length && !matSelectedCategoryId.value) {
      // 不自动选中，保持空选状态
    }
  } catch (e) {
    message.error(`分类加载失败（${e.response?.status || '网络错误'}）`)
  } finally {
    matCategoriesLoading.value = false
  }
}

function onMatCategoryChange(val) {
  matSelectedCategoryId.value = val ?? null
  if (val) loadMatFiles()
  else matFiles.value = []
}

async function loadMatFiles() {
  if (!matSelectedCategoryId.value) {
    matFiles.value = []
    return
  }
  matFilesLoading.value = true
  try {
    const res = await http.get('/api/cn/materials', {
      params: { category_id: matSelectedCategoryId.value },
    })
    matFiles.value = res.data || []
  } catch (e) {
    message.error(`文件列表加载失败（${e.response?.status || '网络错误'}）`)
  } finally {
    matFilesLoading.value = false
  }
}

async function createCategory() {
  const name = newCatName.value.trim()
  if (!name) { message.warning('请填写分类名称'); return }
  catCreating.value = true
  try {
    await http.post('/api/cn/materials/categories', {
      name,
      parent_id: newCatParentId.value || null,
      sort_order: 0,
      type: matTypeTab.value,
    })
    newCatName.value = ''
    newCatParentId.value = null
    message.success('分类已创建')
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '创建失败')
  } finally {
    catCreating.value = false
  }
}

async function deleteCategory(record) {
  if (!window.confirm(`确认删除分类「${record.name}」及其所有子分类？`)) return
  try {
    await http.delete(`/api/cn/materials/categories/${record.id}`)
    message.success('分类已删除')
    if (matSelectedCategoryId.value === record.id) matSelectedCategoryId.value = null
    await loadMatCategories()
    await loadMatFiles()
  } catch (e) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}

function startRename(node) {
  renamingCatId.value = node.id
  renameCatName.value = node.name
}
function cancelRename() {
  renamingCatId.value = null
  renameCatName.value = ''
}
async function saveRename(id) {
  const name = renameCatName.value.trim()
  if (!name) { message.warning('请输入分类名称'); return }
  try {
    await http.patch(`/api/cn/materials/categories/${id}`, { name })
    message.success('已更新')
    cancelRename()
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}
async function onFolderSelected(e) {
  const allFiles = Array.from(e.target.files || [])
  const pdfs = allFiles
  if (!pdfs.length) { message.warning('文件夹内没有文件'); e.target.value = ''; return }
  batchUploading.value = true
  batchResult.value = null
  const formData = new FormData()
  formData.append('type', matTypeTab.value)
  if (matSelectedCategoryId.value) {
    formData.append('parent_category_id', String(matSelectedCategoryId.value))
  }
  for (const f of pdfs) {
    const relPath = f.webkitRelativePath || f.name
    formData.append('files', f, relPath)
  }
  try {
    const res = await http.post('/api/cn/materials/batch_upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    batchResult.value = res.data
    if (res.data.errors?.length) {
      message.warning(`上传完成，${res.data.errors.length} 个文件失败`)
    } else {
      message.success(`已上传 ${res.data.uploaded} 个文件`)
    }
    await loadMatCategories()
    await loadMatFiles()
  } catch (err) {
    message.error(err.response?.data?.detail || '批量上传失败')
  } finally {
    batchUploading.value = false
    e.target.value = ''
  }
}

function beforeGuideUpload(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    message.error('只支持 PDF 文件')
    return false
  }
  return true
}

async function customGuideUpload({ file, onSuccess, onError }) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    await http.post('/api/cn/guide/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    message.success('使用说明已更新')
    onSuccess()
  } catch (e) {
    message.error(e.response?.data?.detail || '上传失败')
    onError(e)
  }
}

function beforeMatUpload(file) {
  if (file.size > MAX_MAT_MB * 1024 * 1024) {
    message.error(`文件超过 ${MAX_MAT_MB}MB 限制`)
    return false
  }
  return true
}

async function customMatUpload({ file, onSuccess, onError }) {
  if (!matSelectedCategoryId.value) {
    onError(new Error('请先选择分类'))
    return
  }
  const formData = new FormData()
  formData.append('category_id', String(matSelectedCategoryId.value))
  formData.append('file', file)
  try {
    await http.post('/api/cn/materials/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    message.success('上传成功')
    onSuccess()
    await loadMatFiles()
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '上传失败')
    onError(e)
  }
}

async function deleteMaterial(id) {
  try {
    await http.delete(`/api/cn/materials/${id}`)
    message.success('已删除')
    await loadMatFiles()
    await loadMatCategories()
  } catch (e) {
    message.error(e.response?.data?.detail || '删除失败')
  }
}

async function deleteAllFiles() {
  if (!matSelectedCategoryId.value || matFiles.value.length === 0) return
  try {
    await Promise.all(
      matFiles.value.map(f =>
        http.delete(`/api/cn/materials/${f.id}`)
      )
    )
    message.success('已删除全部文件')
    await loadMatFiles()
    await loadMatCategories()
  } catch (e) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

watch(activeTab, (tab) => {
  if (tab === 'materials') {
    loadMatCategories().then(loadMatFiles)
  }
})

watch(matTypeTab, () => {
  matSelectedCategoryId.value = null
  matFiles.value = []
  loadMatCategories()
})

onMounted(() => {
  loadStats()
})
</script>

<style lang="less" scoped>
.admin-root {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--cn-bg-page);
}

.admin-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.admin-fail-wrap {
  margin-top: 20px;
}
.admin-feedback-wrap {
  margin-top: 24px;
}
.admin-feedback-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.admin-feedback-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-feedback-item {
  padding: 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
.admin-feedback-head {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}
.admin-feedback-text {
  font-size: 13px;
  color: var(--color-text);
  line-height: 1.6;
}
.admin-feedback-empty {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* Section */
.admin-section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 24px;
}
.admin-section-title,
.admin-mat-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 16px;
  letter-spacing: 0.04em;
}
.admin-section-sub {
  font-weight: 400;
  color: var(--color-text-secondary);
  font-size: 12px;
}

/* Token */
.admin-token-row {
  display: flex;
  gap: 10px;
}
.admin-token-input { flex: 1; }
.admin-error {
  margin-top: 8px;
  font-size: 13px;
  color: #cf1322;
}

/* 统计卡片 */
.admin-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
}
.admin-stat-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 16px;
  text-align: center;
}
.admin-stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-primary);
  margin-bottom: 4px;
}
.admin-stat-label {
  font-size: 11px;
  color: var(--color-text-secondary);
}

/* 未找到记录 */
.admin-fail-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-fail-item {
  padding: 12px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
.admin-fail-question {
  font-size: 14px;
  color: var(--color-text);
  margin-bottom: 6px;
}
.admin-fail-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-secondary);
}

/* 缓存 */
.admin-cache-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.admin-cache-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.admin-cache-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  code {
    background: #f0ece4;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 12px;
    color: var(--color-primary);
  }
}
.admin-clear-result {
  margin-top: 10px;
  font-size: 13px;
  color: #389e0d;
}
.admin-invite-create {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.admin-invite-input {
  flex: 1;
}
.admin-table-wrap {
  overflow-x: auto;
}
.admin-table {
  width: 100%;
  border-collapse: collapse;
  th, td {
    border: 0.5px solid #CCE4F5;
    padding: 8px 10px;
    font-size: 12px;
    color: #1A2A3A;
    text-align: left;
  }
  th {
    background: #EBF4FB;
    font-weight: 600;
    color: #4A6A84;
  }
}
.admin-table-empty {
  text-align: center !important;
  color: var(--color-text-secondary) !important;
}
.admin-placeholder {
  color: var(--color-text-secondary);
  padding: 16px 0;
}
.admin-user-limit-btn {
  margin-right: 8px;
}
.admin-mat-card {
  margin-bottom: 16px;
}
.admin-mat-create {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.admin-mat-input {
  flex: 1;
  min-width: 140px;
}
.admin-mat-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.admin-mat-file-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.admin-mat-file-toolbar-left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.admin-mat-file-toolbar-action {
  width: 80px;
  flex-shrink: 0;
  display: flex;
  justify-content: center;
}
.admin-mat-batch-result {
  font-size: 13px;
  color: #389e0d;
}
.admin-mat-batch-errors {
  color: #cf1322;
}
.admin-mat-file-table {
  margin-top: 0;
  :deep(.ant-table) {
    background: transparent !important;
  }
  :deep(.ant-table-container) {
    background: transparent !important;
  }
  :deep(.ant-table-thead > tr > th) {
    background: var(--cn-bg-page) !important;
    color: var(--cn-text-secondary) !important;
    font-weight: 500 !important;
    border-bottom: 0.5px solid var(--cn-border) !important;
    font-size: 13px !important;
  }
  :deep(.ant-table-tbody > tr > td) {
    font-size: 13px !important;
    padding: 9px 12px !important;
    border-bottom: 0.5px solid var(--cn-border) !important;
    background: var(--cn-bg-card) !important;
  }
  :deep(.ant-table-tbody > tr:hover > td) {
    background: var(--cn-gold-light) !important;
  }
}
.admin-limit-loading {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
}
.admin-limit-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.admin-limit-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.admin-limit-label {
  font-weight: 600;
  font-size: 13px;
}
.admin-limit-hint {
  font-weight: 400;
  color: var(--color-text-secondary);
  font-size: 12px;
}
.admin-limit-usage {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.admin-limit-note {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.admin-mat-tree {
  max-height: 320px;
  overflow-y: auto;
  border: 0.5px solid var(--cn-border);
  border-radius: 6px;
  padding: 6px 0;
  margin-bottom: 12px;
}
.admin-mat-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 10px;
  font-size: 13px;
  border-radius: 4px;
  margin: 1px 4px;
  &:hover { background: #EBF4FB; }
}
.admin-cat-name {
  flex: 1;
  color: var(--cn-text-primary);
}
.admin-cat-count {
  color: var(--cn-text-muted);
  font-size: 12px;
  margin-left: 4px;
}
.admin-cat-arrow {
  font-size: 9px;
  display: inline-block;
  transition: transform 0.2s;
  cursor: pointer;
  &.admin-cat-arrow--open { transform: rotate(90deg); }
}
.admin-cat-actions {
  display: flex;
  gap: 6px;
  opacity: 0;
  .admin-mat-tree-node:hover & { opacity: 1; }
}
.admin-cat-btn {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
  font-family: var(--cn-font);
  margin-left: 6px;
  background: #ffffff;
  border: 1px solid #CCE4F5;
  color: #4A6A84;
  &:hover {
    border-color: #1B6CA8;
    color: #1B6CA8;
    background: #EBF4FB;
  }
  &.admin-cat-btn--danger {
    border: 1px solid #E24B4A !important;
    color: #E24B4A !important;
    background: #ffffff !important;
    &:hover { background: #FEF2F2 !important; }
  }
}
.admin-rename-input {
  flex: 1;
  padding: 2px 8px;
  font-size: 13px;
  border: 0.5px solid var(--cn-border-focus);
  border-radius: 4px;
  font-family: var(--cn-font);
  outline: none;
  margin-right: 6px;
}
.admin-rename-btn {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 0.5px solid var(--cn-border);
  background: transparent;
  cursor: pointer;
  font-family: var(--cn-font);
  &.admin-rename-btn--ok { border-color: var(--cn-gold); color: var(--cn-gold); }
}
.admin-mat-empty {
  padding: 16px;
  text-align: center;
  font-size: 13px;
  color: var(--cn-text-muted);
}
.admin-cat-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  th {
    text-align: left;
    padding: 8px 12px;
    color: #4A6A84;
    font-weight: 600;
    border-bottom: 1px solid #CCE4F5;
    background: #EBF4FB;
  }
  td {
    padding: 9px 12px;
    color: #1A2A3A;
    border-bottom: 1px solid #E0EDF6;
    vertical-align: middle;
  }
  .admin-cat-tr:last-child td { border-bottom: none; }
  .admin-cat-tr:hover td { background: #EBF4FB; }
}
.admin-cat-dir {
  font-family: monospace;
  font-size: 12px;
  color: var(--cn-text-secondary) !important;
}
.admin-cat-meta {
  font-size: 12px;
  color: var(--cn-text-secondary) !important;
}
</style>
