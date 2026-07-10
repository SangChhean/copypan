import {
  CommentOutlined,
  FileTextOutlined,
  BookOutlined,
  FontSizeOutlined,
  CloudDownloadOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'

export const features = [
  {
    key: 'qa',
    title: '职事问答',
    desc: '基于职事信息的智能问答',
    path: '/qa',
    icon: CommentOutlined,
    quotaKey: 'qa',
    building: false,
  },
  {
    key: 'outline',
    title: '纲目制作',
    desc: '基于纲目主题、性质及负担点生成职事纲目',
    path: '/outline',
    icon: FileTextOutlined,
    quotaKey: 'outline',
    building: false,
  },
  {
    key: 'bibco',
    title: '经文汇集',
    desc: '汇集纲目中的所有经文出处，生成带经文的纲目',
    path: '/bibco',
    icon: BookOutlined,
    building: false,
  },
  {
    key: 'zh',
    title: '简繁互转',
    desc: '简繁转换与易错字检查',
    path: '/zh-convert',
    icon: FontSizeOutlined,
    building: false,
  },
  {
    key: 'conference',
    title: '节期特会相关纲目',
    desc: '一年七次节期特会相关的纲目',
    path: '/materials?type=conference',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'pastoral',
    title: '牧养材料',
    desc: '新人、青少年牧养和排聚会的材料',
    path: '/materials?type=pastoral',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'children',
    title: '儿童材料',
    desc: '儿童服事相关的材料',
    path: '/materials?type=children',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'sisters',
    title: '姊妹材料',
    desc: '适合姊妹使用的材料',
    path: '/materials?type=sisters',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'materials',
    title: '资料下载',
    desc: '各类追求材料下载',
    path: '/materials',
    icon: CloudDownloadOutlined,
    building: false,
  },
  {
    key: 'toolbox',
    title: '工具箱',
    desc: '文字服事相关的各类辅助工具',
    path: '/toolbox',
    icon: ToolOutlined,
    building: false,
  },
]

export const HOME_FEATURE_KEYS = ['qa', 'outline', 'materials', 'toolbox']
export const MATERIALS_FEATURE_KEYS = ['pastoral', 'conference', 'children', 'sisters']
export const TOOLBOX_FEATURE_KEYS = ['bibco', 'zh']
