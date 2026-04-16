<script setup>
import { ref, computed, watch, reactive } from "vue";
import { storeToRefs } from "pinia";
import { useStore } from "../store/index";
import { PushpinOutlined, CopyOutlined, CheckOutlined, DownloadOutlined, LoadingOutlined } from "@ant-design/icons-vue";
import axios from "axios";
import { tip } from "./utils/Dialog";
import ShowRes from "./tools/ShowRes.vue";

const plainOptions = [
  { lab: "模糊", val: "a" },
  { lab: "平衡", val: "b" },
  { lab: "精确", val: "c" },
];
const { selectedIndex, showInfo, hilights, refid, openMsg, role } = storeToRefs(useStore());

const selVar1 = ref("a");
const selVar2 = ref("a");
const inputVar = ref("");
const search_cat = ref("a");
const results = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);
const run = ref(false);
const pageSizeOptions = ["10", "20", "30", "40", "50"];
const inputDis = ref(false);
const indexshow = [
  `"属灵的教育也该如此，但我们的科学方法在哪里？我们如何能把圣经的真理，整理出一个系统，当人有心要学习时，可以深入浅出，大小有序，上下连贯，甚至左右相通，前后也没有难处。若是能作到这样，是何等的好。"（李常受文集一九八七年第一册，结常存的果子，第八章）`,
  `"神的话好比拼图。原来，所有的拼图片都是分散的，所要呈现的图画也不明朗。人需要花时间一片接一片的拿起来，仔细思考，并且拼凑在一起。所有的拼图片都拼在一起之后，完整的图画就会出现。神把祂的话这样排列，奥秘又很有意义。"（李常受文集一九七一年第三册，在基督的生命里得救并照着灵而行以建造基督的身体，第三章）`,
  `"（在主的恢复中）你们有的人听我讲道，听到今天（一九八六年）也有三十七年了。当年你们都还是年轻的小弟兄、小姊妹，大都还没有结婚；但是现在你们的儿女都大学毕业了，他们好多人还作了长老。他们还没有出生，你们就已经在这里听我讲道；但是听到今天，你们连小学都没有毕业，原因何在？人类的教育研究出一套制度，需要小学六年、中学六年、大学四年，并且每一年的课程都编得好好地。一个人只要按着这套课程循序渐进的读过，十六年后铁定大学毕业，并且能有系统的把人类中间的常识吸收到他里面。然而这三十七年来，我们在这天花板下讲道给你们听，都是兴之所至，也没有什么系统。所以听到今天，叫你们说一说因信称义，你们一句话也说不出来。这就好像你听了三十七年数学，也知道三加二等于五；可是要你去教别人，就不会教了。"（李常受文集一九八四年第四册，速兴起传福音，第七章）`,
  `"今天的难处是，我们对真理的认识不够，不会介绍真理。到过香港的人都知道，那些卖珠宝玉器的，都会把贵价的珠宝拿出来给人看，等人动心之后，自然愿意出价来买。我们这些基督徒常很愚笨，不懂得拿出真理的宝贝来给人看。我们家里的宝贝实在是多，但我们拿不出来，就因为我们平日的追求和装备不够。因这缘故，我们一定要在召会的聚会里，开辟各种教育课程，教弟兄姊妹在基本上受真理的薰陶，然后出去接触人，个个都有功用。一个国家要强盛，必须教育普及，百姓都受高等教育，这样国家自然强。因为有了教育作底子，作什么就都不难。我们既是为着主的见证，若是我们的真理不强，没有底子，对人说什么都是枉然。反之，有了真理的装备，我们无论说什么，人都会得益处。"（李常受文集一九八五年第五册，为神说话，第七章）`,
  `"我们若要个个传讲真理，尽功用，为着这样的繁增，一定要有分级教育。如此才能培养出传讲真理的人，主日聚会就不怕没有人站讲台，供应话语。弟兄们要带头传讲主的话，众圣徒才有榜样跟随；他们看见后，也会出去对别人传讲。这个风气一开，结果就是众圣徒都能对外讲说主的话；无论是传扬基督、讲解圣经、或释放真理，三、五年后，就会把我们所在地的区域都讲遍了。这是主的作法。我们所交通的，不是要变作教条，叫人一条一条的奉行。我们是盼望众人，将这些交通带回去参考，并且多有祷告。若是有人参考过、祷告之后，在主面前找出更高明的作法，那是最好。原则上，无论如何我们总要帮助圣徒，个个都明白真理。神愿意万人得救，也愿意万人完全认识真理。不仅如此，我们还要帮助圣徒都出去，个个都能作申言者，为主说话。"（李常受文集一九八五年第五册，为神说话，第六章）`,
  `"所以，我这一次来，就愿意把这件事和你们交通清楚，起码我该忠心的告诉你们，我们的程度的确不行。我们要有自觉，知道我们的不行，不要再去谈是非对错的事，那些是不值一题的；值得我们谈论的，乃是我们对真理的认识。要知道，召会的工作起码有百分之五十以上都是教育性的，所以，这一面作得差，就是我们的亏欠和失败。为此，我们今后在这一点上一定要竭力追求。" （李常受文集一九九〇年第二册，神新约经纶中的奥秘，附加的话（一））`,
  `"照着目前的安排，我们在教导和牧养上，有个人的一面，也有团体的一面。往后主日上午若要实行分级真理教育，需要很多会教导的人。我们是盼望所有的人都在话语上下功夫，这样自然能产生出牧养。从前主日几百人的大聚会，都是一人讲。现在作分级真理教育，有分级、分班，班里又分小组；这样，许多人都能尽上功用，也就能产生牧养，使牧养的人渐渐增多。"（李常受文集一九八五年第四册，同心合意实行神命定之路，第二章）`,
  `"我也很坦白说，分级教育很难，因为这里有召会、会所、小排，你怎么分级法？我们也不能铁定的像办教育一样，从小学办起。把小学、初中、高中、大学分得那么清楚。办一所学校，先要把学校建筑起来，要有课室、办公室。以后还得有一班人马，还有教员，还得招生，还有教科书。这个学校才能办得蒸蒸日上，才能成功。在我看，我们学生不成问题；但是在什么地方，怎么作法，这成了很大的问题。"（李常受文集一九八五年第四册，人人要说神的话，第一章）`,
  `"现在，我里头有两个重担：一个是改制，不是已往聚个大聚会就了事；改制，十之八、九要采取现代的教育制度。现代的教育制度：六年小学，三年初中，三年高中，四年大学，二年研究所。这个制度乃是人类六千年各国实施而有的结论。所以今天在地上，没有一个国家不用这一套教育制度，这是铁定的，这是定律。目前我们带得救的人有很多，但是得救以后如何教育他们？怎样训练他们，栽培他们？这成了很大的问题。我接到你们的电话和你们的来信说，前几周，你们这里有福音周，大家出去传福音，总共带了一千一百零四人受浸。这很好，但是受浸完了怎么办？受浸完了就把他们带来这里，拢总在这里聚会，这铁定是不行的。因此我们就得趁机会教育他们。"（李常受文集一九八五年第四册，人人要说神的话，第一章）`,
  `"写出各级的教材来：我觉得材料都有了，但是还需要写出教材来，写出课本来才可以；生命读经有好多丰富，但那还不是教材；你们都读过书，我相信你们也有人作过教员；比如说，数学这一门，材料有了，现在需要有人会写，把重点和路线写出来；六年小学给他们什么东西？国中要给他什么东西？高中又加多一些，大专又加多一些，这数学要一直加的；我们中间不缺少东西，但也必须把教材写出来，不能笼统地写。我们从前是大家吃大锅饭，得救五十八年和得救十八天统统来吃这一锅饭，我们还以这个为夸口，但我们吃来吃去，老的没有了，少的也不长；你们好多人还没有生出来的时候，人数就比今天还多；这样的工我们不能再作了；我们不改制也得改制，因为推不动了；所以这在我身上是一个重担。当然，我没有这么多工夫去作，就得产生弟兄姊妹去作；我们材料都有，但是我们还要出教材，就是出教科书；而生命读经和别的书，都是图书馆里面的书，照样可以作，可以参考，学生也可以去读，我们这样作才能长命；在我看，传福音是不成问题，现在成问题的是怎么养法？不只养，还得教；但怎么教法？现在成了大问题，这就是我们已过失败的点；我盼望你们都了解，今后没有所谓的同工和长老，我们希望个个都是先知，个个都是使徒，个个都是传福音的，个个都是教师，个个都是牧师；现在大家都要来说话，我们今后非生机不可。"（李常受文集一九八五年第四册，人人要说神的话，第一章）`,
  `"在各种聚会中，我们都不轻忽主的话。擘饼聚会可选实用、简要、精粹的信息，让众人祷读、享受，然后分享、作见证；这使主满意，也叫我们得供应。祷告聚会可选关于事奉的信息，让大家清楚事奉的基本属灵原则。至于家中聚会，除了交通、祷告、唱诗、彼此介绍，也该有一篇短的造就信息，让初信者得着栽培。我们不愿意人只是来聚会，对主的话却一无所识，得不着供应；盼望每次的聚会，都有主的话释放到弟兄姊妹里面。这样，每周三篇信息的滋养，加上真理课程有系统、扎实、教育性的教导，就能使圣徒得着帮助并成全。教导时，也要带领圣徒学习看重点。以约翰三章十六节为例，说到神将祂的独生子赐给我们，就要学习点出'赐'这个重点，带圣徒一再读'赐给他们'，加重读、重复读，学习把这个重点指出来。不需要你们特别花工夫去讲解，自然圣徒们就知道重点是什么。我们都必须看见，我们的讲不值钱；只有把主的话拿出来给大家祷读，并且点出重点，那才是有功效的。这样，就给众人有尽功用的机会，而不会闲站。这需要你们在聚会中，一直带领弟兄姊妹操练。我相信最多半年，台北召会就能出来一个规范。"（李常受文集一九八六年第二册，主恢复中划时代的带领，第一册—新路实行的异象与具体步骤，第十七章、第十一章）`,
  `"为这缘故，我觉得有负担召聚这次紧急训练。在美国几乎所有的召会都已听见在台湾所发生的事。你们听见一些事，又听了录音带以后，也许就开始模仿。那是不管用的。你必须领悟这系列中第七册的内容是基本、独一的项目。没有这点，我们就不合格；我们没有立场，甚至没有权利模仿在远东所发生的事。我也要向你们众人指明，家中聚会是什么，全时间是什么，真理课程的教导又是什么。每一项都是难事，不是这么容易完成的。不要轻易模仿，仅仅模仿不管用，只会破坏并危害主的整个行动。现在是迫切、生死的关头。这完全在于你所在之地的长老、助手和同工，要来在一起祷告，找出一条路，得着一位或更多的人，责成他们为每种聚会预备信息，就是活的话。你若有心作，这就不是难事，因为我们在职事的一切信息中有烹调的材料。"（李常受文集一九八六年第一册，长老训练，第八册—主当前行动的命脉，第四章）`,
  `"我不愿为所有的召会预备这样的信息，嘱咐众召会读同样的信息。在美国的许多召会，各召会每主日都需要不同种类的属灵帮助。在主日，不同的召会需要不同的供应。你不能将同样的饭食，供应病房中的每个人。对那些胃有毛病的人，你需要供应某种饭食；对那些心脏有问题的人，你需要供应另一种饭食。你必须有不同的饭食，以喂养不同的人。身为你们所在之地的长老，只有你们才知道你们的家人需要怎样的食物，别人不知道你们家人的需要。这事我考虑得相当多，我觉得必须由每个地方召会个别来作。家庭的烹煮必须由各家个别来作。虽然在原则上，所有的地方召会该是同样的，但在这一面，所有的召会无法是同样的。"（李常受文集一九八六年第一册，长老训练，第八册—主当前行动的命脉，第四章）`,
  `"同工、长老们必须为家中聚会慎选材料。你们一定要花足够的工夫，多方祷告，仔细观察弟兄姊妹的光景，了解（各种）的需要，知道他们聚会的情形，然后再从我们的书报里，寻找适当的材料。就如一个母亲，为家人安排饭食，总要多面顾到他们的光景。有时家人生病了，就要为他预备特别的食物；有时季节转换了，也要有合宜的采购。这些都要研究，都得有一点常识。马太二十四章四十五节说，忠信又精明的奴仆，能按时分粮给神的儿女。这里所说'按时分粮'意义很深，不只要按着时节分给不同的食物，也要按着各人的需要预备不同的食物。这都是必须花工夫研究的事。有时你碰到初信者，也不管他的情形如何，就自顾自的讲起七十个七。你所讲的是神的话不错，但你这一分粮，不是喂养他，而是杀死他。神的话乃是生命；但给你用得不当，就成了杀死人的东西，把人的胃口弄坏了。这样一来，人就不会渴慕聚会了，因为他听到的道，对他没有益处。也许我形容得太过，但我是要给你们看见，你们必须本着'按时分粮'的原则，预备各种聚会的追求信息。这件事非常关系各种聚会的进展。聚会是否使人得益处，是否吸引人，而使人渴慕参加，全在乎这件事。"（李常受文集一九八六年第二册，主恢复中划时代的带领，第一册—新路实行的异象与具体步骤，第十一章）`,
  `"我一直在考虑，在排聚集用什么材料教导人最好。我们有生命课程和真理课程。虽然这些课程写得非常好，我觉得它们不很合式，因为内容太多了，新人不易消化。甚至晨兴圣言也可能不适合在排聚集里的新人。用太多食物喂养人是不好的；我们必须给他们合式的分量。在希伯来五章十二至十四节，保罗提到两种食物，就是奶和干粮。我们不该试图用干粮喂孩子。因此，我们需要有人劳苦，为排聚集编写一些合式的材料，可用作奶来喂养新人。为了使排聚集里的教导和交通有益处，需要有一些材料作为指引。我盼望有些弟兄们被主兴起来，为着排聚集编写一些合式的材料。"（李常受文集一九九一至一九九二年第三册，关于活力排之急切需要的交通，第四章）`,
  `"我们还预备要写二百四十题的生命信息。不是以课合为卷，乃是以辑的方式，每一辑十二篇；二十辑就二百四十篇，都是短短的信息。虽然信息题目，尚不能说全有了，但开头的已经有了。我们盼望主若许可，明年能出版第一辑或第二辑。我们这样忙碌的出版文字，相信大家都不会有安逸的日子。然而，我们也要看见，我们若都过安逸的日子，是作不出工作来的。"（李常受文集一九八七年第一册，结常存的果子，第十五章）`,
];

const cats = {
  a: "全部",
  b: "书名",
  c: "总题",
  d: "篇题",
  e: "标题",
  f: "大纲",
  g: "摘录",
  h: "大本",
  i: "经文",
  j: "注解",
  k: "系列",
  l: "纲目",
  m: "禁用",
};

const get_cats = (val) => {
  let arr = [];
  for (let item of val) {
    arr.push({ lab: cats[item], val: item });
  }
  return arr;
};

const showCats = computed(() => {
  let arr = [];
  let idx = selectedIndex.value[0];

  if (idx == "0") arr = get_cats("abde");
  else if (idx == "1") arr = get_cats("ij");
  else if (idx == "2") arr = get_cats("ade");
  else if (idx == "3") arr = get_cats("abde");
  else if (idx == "4") arr = get_cats("abde");
  else if (idx == "5") arr = get_cats("ade");
  else if (idx == "6") arr = get_cats("h");
  else if (idx == "7") arr = get_cats("acdf");
  else arr = get_cats("m");

  selVar2.value = arr[0].val;
  return arr;
});

const showCatsOne = [
  { lab: "A类", val: "a" },
  { lab: "B类", val: "b" },
];

const status = ref("");
const placeholder = ref("输入搜索内容");

// AI 问答相关状态
const loadingAI = ref(false);
const aiResult = ref(null);
const aiDepth = ref("general"); // 搜索深度：general(一般-50条) 或 deep(深度-200条)
const showAISources = ref(false); // 是否显示引用来源
const showAIAnswer = ref(false); // 是否显示AI答案
const aiLoadingText = ref("AI 正在分析问题..."); // 加载提示文本
// 暂封英文纲目功能，测试通过后改为 true
const ENGLISH_OUTLINE_FEATURE_ENABLED = true;
const includeEnglishOutline = ref(false); // 是否同时生成英文纲目
const answerEn = ref(null); // 英文纲目
const titleEn = ref(null); // 英文标题
const loadingEnglish = ref(false); // 正在生成英文纲目
const errorEnglish = ref(null); // 英文纲目生成失败信息
const aiAnswerEnCopied = ref(false); // 英文复制状态

const includeTraditionalOutline = ref(false); // 是否同时生成繁体纲目
const answerZhTw = ref(null); // 台湾繁体纲目
const loadingTraditional = ref(false); // 正在生成繁体纲目
const errorTraditional = ref(null); // 繁体纲目生成失败信息
const aiAnswerZhTwCopied = ref(false); // 繁体复制状态

// KG-RAG 返回结构化数据
const aiMeta = reactive({
  surface: [],
  deep: [],
  skeleton: null,
  mainSources: [],
  totalElapsedMs: null,
  totalCostUsd: null,
  cached: false,
  cacheKey: null,
});

// 刷格式并下载（DOCX/PDF）
const apiBase = (import.meta.env && import.meta.env.VITE_API_BASE) || "";
const downloadFormatsZh = ref([]);
const downloadFormatsEn = ref([]);
const downloadFormatsZhTw = ref([]);
const downloadingZh = ref(false);
const downloadingEn = ref(false);
const downloadingZhTw = ref(false);

const aiPanelVisible = ref(false);
const AI_NATURE_OPTIONS = ["一般性", "高真理浓度", "高生命浓度", "重实行应用"];
const aiForm = reactive({
  outlineTopic: "",
  burdenDescription: "",
  specialNeeds: "一般性",
  audience: ""
});
const aiFormValid = computed(() => {
  const outline = aiForm.outlineTopic.trim().length > 0;
  const nature = aiForm.specialNeeds.trim().length > 0;
  return outline && nature;
});

// ---------- 两阶段概念抽取 ----------
const conceptStage = ref("idle"); // idle | candidates_ready
const conceptLoading = ref(false);
const conceptCandidates = ref(null);
const selectedSurface = ref([]);
const selectedDeep = ref([]);

watch(
  () => [aiForm.outlineTopic, aiForm.specialNeeds, aiForm.burdenDescription, aiForm.audience],
  () => {
    if (conceptStage.value !== "idle") {
      conceptStage.value = "idle";
      conceptCandidates.value = null;
      selectedSurface.value = [];
      selectedDeep.value = [];
    }
  }
);

async function extractConcepts() {
  const q = aiForm.outlineTopic.trim();
  if (!q) { tip("请填写纲目主题"); return; }
  conceptLoading.value = true;
  try {
    const res = await axios.post("/api/kg_rag/extract_concepts", {
      query: q,
      outline_nature: aiForm.specialNeeds.trim(),
      burden_description: aiForm.burdenDescription.trim(),
      audience: aiForm.audience.trim(),
    });
    conceptCandidates.value = res.data;
    selectedSurface.value = [...(res.data.surface || [])];
    selectedDeep.value = [...(res.data.deep_candidates || [])];
    conceptStage.value = "candidates_ready";
  } catch (e) {
    tip(e.response?.data?.error || e.message || "概念抽取失败");
  } finally {
    conceptLoading.value = false;
  }
}

function resetConceptState() {
  conceptStage.value = "idle";
  conceptCandidates.value = null;
  selectedSurface.value = [];
  selectedDeep.value = [];
}

// AI 回答复制（包含标题）
const aiAnswerCopied = ref(false);
const copyAiAnswer = async () => {
  const text = aiResult.value?.answer;
  if (!text) return;
  // 使用生成时保存的标题，而不是当前输入框的值
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  try {
    await navigator.clipboard.writeText(fullText);
    aiAnswerCopied.value = true;
    tip("已复制到剪贴板");
    setTimeout(() => {
      aiAnswerCopied.value = false;
    }, 2000);
  } catch (e) {
    tip("复制失败");
  }
};

// 英文纲目复制（包含标题）
const copyAiAnswerEn = async () => {
  const text = answerEn.value;
  if (!text) return;
  // 优先使用英文标题，否则使用生成时保存的中文标题
  const title = titleEn.value || aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  try {
    await navigator.clipboard.writeText(fullText);
    aiAnswerEnCopied.value = true;
    tip("英文纲目已复制到剪贴板");
    setTimeout(() => {
      aiAnswerEnCopied.value = false;
    }, 2000);
  } catch (e) {
    tip("复制失败");
  }
};

// 请求翻译中文纲目为英文（用户勾选「同时生成英文纲目」后调用）
const fetchTranslate = async (chineseOutline) => {
  if (!chineseOutline || !chineseOutline.trim()) return;
  loadingEnglish.value = true;
  errorEnglish.value = null;
  answerEn.value = null;
  titleEn.value = null;
  try {
    const res = await axios.post(
      "/api/ai_search/translate_outline",
      { 
        chinese_outline: chineseOutline,
        outline_topic: aiForm.outlineTopic.trim() || null
      },
      { timeout: 120000 }
    );
    const data = res.data;
    if (data.answer_en) {
      answerEn.value = data.answer_en;
      titleEn.value = (data.title_en && data.title_en.trim()) ? data.title_en.trim() : null;
      if (!titleEn.value) {
        console.warn("英文标题翻译未返回，将使用中文标题");
      }
      if (aiMeta.cacheKey) {
        axios.post("/api/kg_rag/cache_translation", {
          cache_key: aiMeta.cacheKey,
          field: "answer_en",
          value: data.answer_en,
        }).catch(() => {});
      }
    } else {
      errorEnglish.value = data.error || "英文纲目生成失败";
    }
  } catch (err) {
    errorEnglish.value = err.response?.data?.detail || err.message || "翻译请求失败，请稍后重试";
  } finally {
    loadingEnglish.value = false;
  }
};

// 请求简体纲目转台湾繁体（用户勾选「同时生成繁体纲目」后调用）
const fetchTraditionalOutline = async (simplifiedOutline) => {
  if (!simplifiedOutline || !simplifiedOutline.trim()) return;
  loadingTraditional.value = true;
  errorTraditional.value = null;
  answerZhTw.value = null;
  try {
    const res = await axios.post(
      "/api/ai_search/outline_to_traditional",
      { content: simplifiedOutline },
      { timeout: 60000 }
    );
    const data = res.data;
    if (data.answer_zh_tw) {
      answerZhTw.value = data.answer_zh_tw;
      if (aiMeta.cacheKey) {
        axios.post("/api/kg_rag/cache_translation", {
          cache_key: aiMeta.cacheKey,
          field: "answer_zh_tw",
          value: data.answer_zh_tw,
        }).catch(() => {});
      }
    } else {
      errorTraditional.value = data.error || "繁体纲目生成失败";
    }
  } catch (err) {
    errorTraditional.value = err.response?.data?.detail || err.message || "简转繁请求失败，请稍后重试";
  } finally {
    loadingTraditional.value = false;
  }
};

// 繁体纲目复制（包含标题）
const copyAiAnswerZhTw = async () => {
  const text = answerZhTw.value;
  if (!text) return;
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  try {
    await navigator.clipboard.writeText(fullText);
    aiAnswerZhTwCopied.value = true;
    tip("繁体纲目已复制到剪贴板");
    setTimeout(() => {
      aiAnswerZhTwCopied.value = false;
    }, 2000);
  } catch (e) {
    tip("复制失败");
  }
};

// 刷格式并下载（中文纲目）
const downloadFormattedZh = async () => {
  const text = aiResult.value?.answer;
  if (!text || downloadFormatsZh.value.length === 0) {
    if (!text) tip("请先完成纲目生成");
    else tip("请至少选择一种下载格式");
    return;
  }
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  downloadingZh.value = true;
  try {
    const orderedZh = ["docx", "pdf"].filter((f) => downloadFormatsZh.value.includes(f));
    for (const format of orderedZh) {
      const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ direction: "en2zh", translated_text: fullText, output_format: format }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tip((data.detail || data.error) || "格式化失败");
        continue;
      }
      doDownload(data, format, false);
    }
    if (downloadFormatsZh.value.length > 0) tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  } finally {
    downloadingZh.value = false;
  }
};

// 刷格式并下载（英文纲目）
const downloadFormattedEn = async () => {
  const text = answerEn.value;
  if (!text || downloadFormatsEn.value.length === 0) {
    if (!text) tip("请先完成英文纲目生成");
    else tip("请至少选择一种下载格式");
    return;
  }
  const title = titleEn.value || aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  downloadingEn.value = true;
  try {
    const orderedEn = ["docx", "pdf"].filter((f) => downloadFormatsEn.value.includes(f));
    for (const format of orderedEn) {
      const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ direction: "zh2en", translated_text: fullText, output_format: format }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tip((data.detail || data.error) || "格式化失败");
        continue;
      }
      doDownload(data, format, true);
    }
    if (downloadFormatsEn.value.length > 0) tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  } finally {
    downloadingEn.value = false;
  }
};

// 刷格式并下载（繁体纲目）
const downloadFormattedZhTw = async () => {
  const text = answerZhTw.value;
  if (!text || downloadFormatsZhTw.value.length === 0) {
    if (!text) tip("请先完成繁体纲目生成");
    else tip("请至少选择一种下载格式");
    return;
  }
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  const fullText = title ? `${title}\n\n${text}` : text;
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.hash = "/login";
    return;
  }
  downloadingZhTw.value = true;
  try {
    const orderedZhTw = ["docx", "pdf"].filter((f) => downloadFormatsZhTw.value.includes(f));
    for (const format of orderedZhTw) {
      const res = await fetch(`${apiBase}/api/ai_search/format_outline_only`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ direction: "zh_cn2tw", translated_text: fullText, output_format: format }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        tip((data.detail || data.error) || "格式化失败");
        continue;
      }
      doDownload(data, format, false);
    }
    if (downloadFormatsZhTw.value.length > 0) tip("下载完成");
  } catch (e) {
    tip(e?.message || "下载失败");
  } finally {
    downloadingZhTw.value = false;
  }
};

// 通用：根据接口返回触发 DOCX/PDF 下载（移动端与桌面端均使用下载）
function doDownload(data, format, isEn) {
  const defaultName = isEn ? "outline_en" : "outline_zh";
  if (format === "docx" && data.docx_base64) {
    const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
    const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.filename || `${defaultName}.docx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (format === "pdf") {
    if (data.pdf_base64) {
      const bin = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || `${defaultName}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else if (data.docx_base64) {
      const bin = Uint8Array.from(atob(data.docx_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bin], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = (data.filename || defaultName).replace(".pdf", ".docx");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      tip("PDF 转换失败，已下载 DOCX");
    }
  }
}

// 仅将 AI 回答中的大点（壹、贰、叁/参…拾、拾壹、拾贰…贰拾、贰壹、贰贰…）整行加粗；「参考与参读资料：」及之后不加粗
const aiAnswerFormatted = computed(() => {
  const raw = aiResult.value?.answer;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  // 「参考与参读资料：」及之后不加粗
  const refIdx = withBr.search(/参考与参读资料[：:]/i);
  const toBold = refIdx >= 0 ? withBr.slice(0, refIdx) : withBr;
  const afterRef = refIdx >= 0 ? withBr.slice(refIdx) : "";
  // 只匹配大点：壹、贰、叁/参、肆…拾、拾壹、拾贰…贰拾、贰壹、贰贰… 整行（纲目后可为顿号、逗号、全角空格、半角空格、制表符等）
  const big = /(^|<br>)([\s#*]*)((?:壹[、，\u3000\t ]|贰[、，\u3000\t ]|(?:叁|参)[、，\u3000\t ]|肆[、，\u3000\t ]|伍[、，\u3000\t ]|陆[、，\u3000\t ]|柒[、，\u3000\t ]|捌[、，\u3000\t ]|玖[、，\u3000\t ]|拾[、，\u3000\t ]|拾[壹贰叁参肆伍陆柒捌玖][、，\u3000\t ]|贰[拾壹贰叁参肆伍陆柒捌玖][、，\u3000\t ])[^<]*?)(?=<br>|$)/g;
  const s = toBold.replace(big, "$1$2<strong>$3</strong>");
  const content = s + afterRef;
  // 添加标题（如果有）- 使用生成时保存的标题，而不是当前输入框的值
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  if (title) {
    const titleEscaped = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div style="text-align: center; font-weight: bold; margin-bottom: 16px;">${titleEscaped}</div>${content}`;
  }
  return content;
});

// 繁体纲目格式化（换行转 br，大点壹貳參…加粗，「參考與參讀資料：」及之后不加粗）
const aiAnswerZhTwFormatted = computed(() => {
  const raw = answerZhTw.value;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  const refIdx = withBr.search(/參考與參讀資料[：:]/i);
  const toBold = refIdx >= 0 ? withBr.slice(0, refIdx) : withBr;
  const afterRef = refIdx >= 0 ? withBr.slice(refIdx) : "";
  // 繁体大点：壹、貳、參、肆、伍、陸、柒、捌、玖、拾、拾壹…貳拾、貳壹…
  const big = /(^|<br>)([\s#*]*)((?:壹[、，\u3000\t ]|貳[、，\u3000\t ]|參[、，\u3000\t ]|肆[、，\u3000\t ]|伍[、，\u3000\t ]|陸[、，\u3000\t ]|柒[、，\u3000\t ]|捌[、，\u3000\t ]|玖[、，\u3000\t ]|拾[、，\u3000\t ]|拾[壹貳參肆伍陸柒捌玖][、，\u3000\t ]|貳[拾壹貳參肆伍陸柒捌玖][、，\u3000\t ])[^<]*?)(?=<br>|$)/g;
  const s = toBold.replace(big, "$1$2<strong>$3</strong>");
  const content = s + afterRef;
  const title = aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  if (title) {
    const titleEscaped = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div style="text-align: center; font-weight: bold; margin-bottom: 16px;">${titleEscaped}</div>${content}`;
  }
  return content;
});

// 英文纲目格式化（换行转 br，只有英文大点加粗，其他星号去掉）
const aiAnswerEnFormatted = computed(() => {
  const raw = answerEn.value;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  // 英文大点罗马数字：I–X(1–10)、XI–XX(11–20)，支持加粗
  const romanMajor = "(?:XX|X(?:I{0,3}|IV|VI{0,3}|IX)?|I{1,3}|IV|VI{0,3}|IX|X)";
  // 先处理带星号的英文大点（**I.**、**XI.** 等）加粗
  const withBoldStars = withBr.replace(new RegExp(`\\*\\*(${romanMajor}[\\.:]\\s*[^<]*?)\\*\\*`, "g"), "<strong>$1</strong>");
  // 将剩余的 **文本** 去掉星号，只保留文本（不加粗）
  const withoutBold = withBoldStars.replace(/\*\*([^*]+?)\*\*/g, "$1");
  // 将 Markdown 的 *文本*（斜体）去掉星号，只保留文本
  const withoutItalic = withoutBold.replace(/\*([^*]+?)\*/g, "$1");
  // 直接匹配英文大点（I–X、XI–XX）加粗（不依赖星号）
  const bigEn = new RegExp(`(^|<br>)([\\s#*]*)(${romanMajor}[\\.:]\\s*[^<]*?)(?=<br>|$)`, "g");
  const content = withoutItalic.replace(bigEn, "$1$2<strong>$3</strong>");
  // 添加标题（如果有）- 优先使用英文标题，否则使用生成时保存的中文标题
  const title = titleEn.value || aiResult.value?.outlineTopic || aiForm.outlineTopic.trim();
  if (title) {
    const titleEscaped = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<div style="text-align: center; font-weight: bold; margin-bottom: 16px;">${titleEscaped}</div>${content}`;
  }
  return content;
});

// ─── 引用来源：索引类型判断与格式化 ───

function getSourceType(chunkId) {
  if (!chunkId) return "unknown";
  if (chunkId.startsWith("firewall:") || chunkId.startsWith("防火墙")) return "firewall";
  if (chunkId.startsWith("life_")) return "life";
  if (chunkId.startsWith("cwwl_")) return "cwwl";
  if (chunkId.startsWith("cwwn_")) return "cwwn";
  if (chunkId.startsWith("others_")) return "others";
  if (chunkId.startsWith("bib_")) return "bib";
  if (chunkId.startsWith("map_note_")) return "map_note";
  if (chunkId.startsWith("map_7feasts_")) return "map_7feasts";
  if (chunkId.startsWith("map_pano")) return "map_pano";
  if (chunkId.startsWith("map_dictionary")) return "map_dictionary";
  return "unknown";
}

const SOURCE_TYPE_LABELS = {
  firewall:       { label: "防火墙",         color: "#f50" },
  life:           { label: "生命读经",       color: "#2db7f5" },
  cwwl:           { label: "李常受文集",     color: "#87d068" },
  cwwn:           { label: "倪柝声文集",     color: "#9254de" },
  others:         { label: "其他",           color: "#13c2c2" },
  bib:            { label: "圣经",           color: "#fa8c16" },
  map_note:       { label: "注解纲目",       color: "#597ef7" },
  map_7feasts:    { label: "节期纲目",       color: "#f759ab" },
  map_pano:       { label: "清明上河图",     color: "#36cfc9" },
  map_dictionary: { label: "主恢复真理词典", color: "#ff85c0" },
  unknown:        { label: "其他",           color: "#d9d9d9" },
};

function getSourceLabel(chunkId) {
  return SOURCE_TYPE_LABELS[getSourceType(chunkId)] || SOURCE_TYPE_LABELS.unknown;
}

function formatSourceTitle(src) {
  const type = getSourceType(src.chunk_id);

  if (type === "firewall") {
    return src.chunk_id.replace(/^firewall:/, "");
  }

  if (type === "bib") {
    const sz = src.source_zh || src.chunk_id;
    return sz.replace(/^[（(]/, "").replace(/[）)]$/, "");
  }

  const parts = [];
  if (src.book_title) parts.push(src.book_title);
  if (src.message_title) parts.push(src.message_title);
  return parts.join("，") || src.chunk_id;
}

const toggleAiPanel = () => {
  aiPanelVisible.value = !aiPanelVisible.value;
  if (aiPanelVisible.value) {
    inputVar.value = "";
    status.value = "";
  }
};

const buildKgRagParams = () => ({
  outline_nature: aiForm.specialNeeds.trim(),
  burden_description: aiForm.burdenDescription.trim(),
  audience: aiForm.audience.trim(),
  depth: aiDepth.value,
});

const onSearch = (inp) => {
  if (!run.value) run.value = true;
  showInfo.value = 4;
  let input = inputVar.value.trim();

  if (input == "") {
    status.value = "error";
    placeholder.value = "搜索内容不能为空";
    showInfo.value = 3;
    return;
  }

  let index = selectedIndex.value[0];
  let cat1 = selVar1.value;
  let cat2 = selVar2.value;
  let model = search_cat.value;
  let cp = currentPage.value;
  let ps = pageSize.value;

  if (selVar2.value == "m") {
    showInfo.value = 3;
    inputDis.value = true;
    return;
  }

  let sta = "";
  if (index == "0") sta = cat1;
  else sta = index;

  hilights.value = input.split(/ +/g);

  let args = `${sta}-${cat2}-${model}-${cp}-${ps}`;
  let formData = new FormData();
  formData.append("input", input);
  formData.append("args", args);

  let token = localStorage.getItem("token") || null;
  axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  axios
    .post("/api/search", formData)
    .then((res) => {
      let data = res.data;
      total.value = data.total;
      results.value = data.msg;
      if (data.msg == "pass") return;
      if (total.value == 0) {
        showInfo.value = 3;
      } else {
        showInfo.value = 2;
      }
    })
    .catch((err) => {
      if (err?.response?.status == 401) {
        window.location.hash = "/login";
      }
      showInfo.value = 3;
    });
};

const onChange = () => {
  status.value = "";
  placeholder.value = "输入搜索内容";
};

const openmsg = (val) => {
  if (!val) return;
  refid.value = val;
  openMsg.value = !openMsg.value;
};

const onChangePage = (page, pageSize) => {
  onSearch("");
};

const showSizeChange = (current, size) => {
  onSearch("");
};

watch([selVar1, selVar2, search_cat, selectedIndex], () => {
  if (selVar2.value == "m") {
    inputDis.value = true;
  } else {
    inputDis.value = false;
    onSearch("");
  }
  currentPage.value = 1;
});

const change_icon = (val) => {
  let dom = document.getElementById(val);
  let span1 = dom.getElementsByTagName("span")[0];
  let span2 = dom.getElementsByTagName("span")[1];

  span1.setAttribute("style", "display: none");
  span2.setAttribute("style", "display: inline-block");

  setTimeout(() => {
    span1.setAttribute("style", "display: inline-block");
    span2.setAttribute("style", "display: none");
  }, 2000);
};

const copyText = (val) => {
  if (!val) return;
  val = val.replace(/<[^>]*>/g, "");
  navigator.clipboard.writeText(val);
  tip("复制成功");
};

const copyTextAndChnageIcon = (val, id) => {
  copyText(val);
  change_icon(id);
};

const addTag = (val) => {
  let arr = [];
  let cid = val[0][1];
  let index = cid.split("_")[0];
  console.log(index);
  if (["life", "cwwn"].includes(index)) {
    arr.push(["查看整篇", cid]);
    arr.push(["只看大纲", cid + "-outline"]);
    arr.push(["只看标题", cid + "-heading"]);
    return arr;
  } else return val;
};

/** 统一解析 KG-RAG 响应（缓存命中 / 未命中） */
function parseKgRagResponse(data) {
  const isCached = !!data.cached;
  const result = {
    answer: data.answer || null,
    outlineTopic: aiForm.outlineTopic.trim(),
    cached: isCached,
    cacheKey: data.cache_key || null,
    surface: [],
    deep: [],
    skeleton: null,
    mainSources: [],
    totalElapsedMs: null,
    totalCostUsd: null,
    answerEn: null,
    answerZhTw: null,
  };
  if (isCached) {
    result.surface = data.surface || [];
    result.deep = data.deep || [];
    result.skeleton = data.skeleton || null;
    result.mainSources = data.main_sources || [];
    result.totalElapsedMs = data.total_elapsed_ms ?? null;
    result.totalCostUsd = data.total_cost_usd ?? null;
    result.answerEn = data.answer_en || null;
    result.answerZhTw = data.answer_zh_tw || null;
  } else {
    const s1 = data.steps?.step1 || {};
    const s2 = data.steps?.step2 || {};
    const s3 = data.steps?.step3 || {};
    const usage = data.llm_usage || {};
    result.surface = s1.surface || [];
    result.deep = s1.deep || [];
    result.skeleton = s2.skeleton || null;
    result.mainSources = (s3.main_results || []).map(r => ({
      chunk_id: r.chunk_id || "",
      book_title: r.book_title || "",
      source_zh: r.source_zh || "",
      message_title: r.message_title || "",
      text_preview: (() => {
        const t = r.text || "";
        return t.length > 200 ? t.slice(0, 200) + "…" : t;
      })(),
    }));
    result.totalElapsedMs = usage.total_elapsed_ms ?? null;
    result.totalCostUsd = (usage.totals || {}).cost_usd ?? null;
  }
  return result;
}

// AI 纲目生成（单次调用 KG-RAG）
const onAISearch = async () => {
  const question = aiForm.outlineTopic.trim();

  if (!question || !aiFormValid.value) {
    tip("请至少填写纲目主题并选择纲目性质");
    return;
  }

  loadingAI.value = true;
  showInfo.value = 6;
  aiResult.value = null;
  answerEn.value = null;
  errorEnglish.value = null;
  answerZhTw.value = null;
  errorTraditional.value = null;
  showAISources.value = false;
  showAIAnswer.value = false;
  aiLoadingText.value = "✨ AI 纲目生成中…";
  Object.assign(aiMeta, { surface: [], deep: [], skeleton: null, mainSources: [], totalElapsedMs: null, totalCostUsd: null, cached: false, cacheKey: null });

  try {
    const qParams = buildKgRagParams();
    if (conceptStage.value === "candidates_ready" && conceptCandidates.value && selectedDeep.value.length > 0) {
      qParams.preset_surface = selectedSurface.value;
      qParams.preset_deep = selectedDeep.value;
    }
    const res = await axios.post(
      "/api/kg_rag/query",
      { query: question, params: qParams },
      { timeout: 300000 }
    );
    const data = res.data;
    if (!data.answer) {
      tip(data.error || "纲目生成失败，请稍后重试");
      showInfo.value = 3;
      return;
    }

    const parsed = parseKgRagResponse(data);
    aiResult.value = { answer: parsed.answer, outlineTopic: parsed.outlineTopic };
    Object.assign(aiMeta, {
      surface: parsed.surface,
      deep: parsed.deep,
      skeleton: parsed.skeleton,
      mainSources: parsed.mainSources,
      totalElapsedMs: parsed.totalElapsedMs,
      totalCostUsd: parsed.totalCostUsd,
      cached: parsed.cached,
      cacheKey: parsed.cacheKey,
    });

    showInfo.value = 5;
    showAISources.value = true;
    showAIAnswer.value = true;

    if (parsed.cached) {
      aiLoadingText.value = "已找到缓存结果";
    }

    // 缓存命中且已有翻译时直接展示
    if (parsed.cached && parsed.answerEn) {
      answerEn.value = parsed.answerEn;
    } else if (includeEnglishOutline.value) {
      fetchTranslate(parsed.answer);
    }
    if (parsed.cached && parsed.answerZhTw) {
      answerZhTw.value = parsed.answerZhTw;
    } else if (includeTraditionalOutline.value) {
      fetchTraditionalOutline(parsed.answer);
    }

    setTimeout(() => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }, 100);
  } catch (err) {
    console.error("AI纲目生成失败:", err);
    const isTimeout = err.code === "ECONNABORTED" || err.message?.includes("timeout");
    const msg = isTimeout
      ? "请求超时，AI 生成时间较长，请稍后重试"
      : (err.response?.data?.detail || err.response?.data?.error || "AI纲目生成失败，请稍后重试");
    tip(msg);
    showInfo.value = 3;
  } finally {
    loadingAI.value = false;
    resetConceptState();
  }
};
</script>

<template>
  <div class="search-box">
    <div class="search-bar">
      <div class="search">
        <a-input-search
          :disabled="inputDis || aiPanelVisible"
          v-model:value="inputVar"
          :status="status"
          :placeholder="aiPanelVisible ? 'AI纲目模式：问题将根据纲目主题生成' : placeholder"
          enter-button
          @search="onSearch"
          @change="onChange"
          allowClear
        >
          <template #addonBefore>
            <a-select v-model:value="selVar1" :showArrow="false" v-if="selectedIndex[0] == '0'" :style="{ width: '60px' }" :bordered="false">
              <a-select-option v-for="item in showCatsOne" :value="item.val">{{ item.lab }}</a-select-option>
            </a-select>
            <span v-if="selectedIndex[0] == '0'"> / </span>
            <a-select v-model:value="selVar2" :showArrow="false" :bordered="false" :style="{ width: '60px' }">
              <a-select-option v-for="item in showCats" :value="item.val">{{ item.lab }}</a-select-option>
            </a-select>
          </template>
        </a-input-search>
      </div>
      <div class="model">
        <a-radio-group v-model:value="search_cat" button-style="solid">
          <a-radio-button v-for="item in plainOptions" :value="item.val">{{ item.lab }}</a-radio-button>
        </a-radio-group>
        <a-button 
          type="primary" 
          :loading="loadingAI" 
          @click="toggleAiPanel" 
          style="margin-left: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"
        >
          {{ aiPanelVisible ? "收起AI纲目面板" : "AI纲目制作面板" }}
        </a-button>
      </div>
      <transition name="ai-meta-panel">
        <div v-if="aiPanelVisible" class="ai-meta-panel">
          <span class="ai-panel-brand">Pan AI 3.0</span>
          <div class="ai-meta-grid">
            <label class="ai-meta-field">
              <span>纲目主题*（必填）</span>
              <input
                type="text"
                v-model="aiForm.outlineTopic"
                :disabled="loadingAI"
                placeholder="纲目的题目"
              />
            </label>
            <label class="ai-meta-field">
              <span>面对对象</span>
              <input
                type="text"
                v-model="aiForm.audience"
                :disabled="loadingAI"
                placeholder="例如：一般性、初信者、大专学生..."
              />
            </label>
            <label class="ai-meta-field full">
              <span>负担说明/简单摘要（50字）</span>
              <textarea
                class="ai-burden-textarea"
                rows="5"
                v-model="aiForm.burdenDescription"
                :disabled="loadingAI"
                placeholder="约50字概括纲目摘要，说明纲目负担"
              ></textarea>
            </label>
            <div class="ai-meta-field full">
              <span>纲目性质*（必选）</span>
              <div class="ai-nature-btns">
                <button
                  type="button"
                  v-for="opt in AI_NATURE_OPTIONS"
                  :key="opt"
                  :class="['ai-nature-btn', { active: aiForm.specialNeeds === opt }]"
                  :disabled="loadingAI"
                  @click="aiForm.specialNeeds = aiForm.specialNeeds === opt ? '' : opt"
                >
                  {{ opt }}
                </button>
              </div>
            </div>
          </div>
            <div class="ai-panel-actions">
            <div class="ai-panel-hint" v-if="!aiFormValid">请至少填写纲目主题并选择纲目性质后再开始制作</div>
            <!-- 概念候选面板 -->
            <div v-if="conceptStage === 'candidates_ready' && conceptCandidates" class="ai-concept-panel">
              <div class="ai-concept-hint">以下是 AI 识别到的相关概念，请勾选确认后生成纲目</div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">字面意义层：</span>
                <a-checkbox-group v-model:value="selectedSurface" class="ai-concept-checks">
                  <a-checkbox v-for="s in conceptCandidates.surface" :key="s" :value="s">{{ s }}</a-checkbox>
                </a-checkbox-group>
                <span v-if="!conceptCandidates.surface?.length" class="ai-concept-empty">（无）</span>
              </div>
              <div class="ai-concept-section">
                <span class="ai-concept-label">内在意义层：</span>
                <a-checkbox-group v-model:value="selectedDeep" class="ai-concept-checks">
                  <a-checkbox v-for="d in conceptCandidates.deep_candidates" :key="d" :value="d">{{ d }}</a-checkbox>
                </a-checkbox-group>
              </div>
              <div v-if="conceptCandidates.reasoning" class="ai-concept-reasoning">{{ conceptCandidates.reasoning }}</div>
              <div v-if="selectedDeep.length === 0" class="ai-concept-warn">请至少选择一个内在意义</div>
            </div>
            <div class="ai-panel-cta">
              <div class="ai-depth-inline">
                <span>模式选择</span>
                <a-radio-group v-model:value="aiDepth" button-style="solid">
                  <a-radio-button value="general">普通</a-radio-button>
                  <a-radio-button value="deep">深度</a-radio-button>
                </a-radio-group>
              </div>
              <a-checkbox v-model:checked="includeEnglishOutline" :disabled="!ENGLISH_OUTLINE_FEATURE_ENABLED || loadingAI" style="margin-right: 12px;">同时生成英文纲目</a-checkbox>
              <a-checkbox v-model:checked="includeTraditionalOutline" :disabled="loadingAI" style="margin-right: 12px;">同时生成繁体纲目</a-checkbox>
              <a-button
                v-if="conceptStage === 'idle'"
                :loading="conceptLoading"
                :disabled="conceptLoading || !aiFormValid"
                @click="extractConcepts"
              >
                {{ conceptLoading ? "抽取中…" : "抽取概念" }}
              </a-button>
              <a-button
                v-else
                type="primary"
                :loading="loadingAI"
                :disabled="loadingAI || selectedDeep.length === 0"
                @click="onAISearch"
              >
                {{ loadingAI ? "生成中…" : "生成纲目" }}
              </a-button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
  <a-divider style="margin: 30px 0 10px 0"></a-divider>
  <div class="info" v-if="showInfo == 1">
    <div class="cat">
      <div>A类：经文、注解、生命读经、倪文集、李文集、其他</div>
      <div>B类：A类、诗歌、节期</div>
    </div>
    <div class="paoma">
      <a-carousel autoplay>
        <div class="textindex" v-for="item in indexshow" v-html="item"></div>
      </a-carousel>
    </div>
    <div style="margin-bottom: 80px"></div>
    <!-- <div class="footer_fix">© 臺灣福音書房 | © Living Stream Ministry</div> -->
  </div>
  <div class="search-result" v-if="showInfo == 2">
    <a-alert type="success" show-icon>
      <template #message>
        <span style="font-size: 16px">
          共搜索到 <em>{{ total }}</em> 条
        </span>
      </template>
    </a-alert>
    <a-divider style="margin: 10px 0"></a-divider>
    <div v-for="item in results" class="res">
      <div class="res-header">
        <a-space :size="[0, 'small']" wrap class="space">
          <a-tag color="purple" :bordered="false" v-for="tag in addTag(item.tags)" class="tag" @click="openmsg(tag[1])">
            <template #icon>
              <PushpinOutlined />
            </template>
            {{ tag[0] }}
          </a-tag>
        </a-space>
      </div>
      <a-divider style="margin: 3px 0"></a-divider>
      <div class="res-title">
        <span v-text="item.title"></span>
        <span v-if="role == 't0'" style="margin-left: 10px"><a-button v-text="item.id" size="small" @click="copyText(item.id)" type="primary" ghost></a-button></span>
      </div>
      <a-divider style="margin: 3px 0"></a-divider>
      <div class="res-body">
        <div class="up" v-if="item.up">
          <span v-html="item.up"></span>
          <a-tag color="blue" :bordered="false" @click="copyTextAndChnageIcon(item.up, item.id + 'up')" class="text_tag">
            <template #icon>
              <div :id="item.id + 'up'">
                <CopyOutlined />
                <CheckOutlined style="display: none" />
              </div>
            </template>
          </a-tag>
          <a-divider style="margin: 3px 0"></a-divider>
        </div>

        <div class="down" v-if="item.down">
          <span v-html="item.down"></span>
          <a-tag color="blue" :bordered="false" @click="copyTextAndChnageIcon(item.down, item.id + 'down')" class="text_tag">
            <template #icon>
              <div :id="item.id + 'down'">
                <CopyOutlined />
                <CheckOutlined style="display: none" />
              </div>
            </template>
          </a-tag>
          <a-divider style="margin: 3px 0"></a-divider>
        </div>
      </div>

      <div class="res-footer">
        <a-space :size="[7, 'small']" wrap class="space">
          <span v-for="sorc in item.source" class="tag_footer" color="pink" :bordered="false" @click="copyText(sorc)">{{ sorc }}</span>
        </a-space>
      </div>
    </div>
    <div class="pages">
      <a-divider></a-divider>
      <a-pagination :pageSizeOptions="pageSizeOptions" v-model:current="currentPage" size="small" :total="total" v-model:page-size="pageSize" show-size-changer show-quick-jumper @change="onChangePage" @showSizeChange="showSizeChange" />
    </div>
    <div style="margin-bottom: 360px"></div>
  </div>
  <!-- AI 正在思考的加载动画 -->
  <div class="ai-loading-container" v-if="showInfo == 6">
    <div class="ai-loading">
      <div class="ai-loading-card">
        <div class="loading-content">
          <a-spin size="large">
            <template #indicator>
              <div class="custom-spinner">
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
                <div class="spinner-dot"></div>
              </div>
            </template>
          </a-spin>
          <div class="loading-text">{{ aiLoadingText }}</div>
          <div class="loading-tips">
            <span v-if="aiDepth === 'general'">正在使用一般模式</span>
            <span v-else>正在使用深度模式</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- AI 问答结果显示 -->
  <div class="ai-result" v-if="showInfo == 5 && aiResult">
    <a-alert type="success" show-icon>
      <template #message>
        <span style="font-size: 16px">✨ <strong style="background: linear-gradient(135deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">Pan AI 3.0</strong> 纲目生成完成</span>
      </template>
    </a-alert>
    <a-divider style="margin: 10px 0"></a-divider>

    <!-- 信息栏：耗时 / 费用 / 缓存 / 概念 / 骨架 -->
    <div class="kg-info-bar">
      <div class="kg-info-stats">
        <span v-if="aiMeta.totalElapsedMs != null">⏱ 耗时 <strong>{{ (aiMeta.totalElapsedMs / 1000).toFixed(1) }}s</strong></span>
        <span v-if="aiMeta.totalCostUsd != null" class="kg-info-sep">💰 <strong>${{ Number(aiMeta.totalCostUsd).toFixed(2) }}</strong></span>
        <a-tag v-if="aiMeta.cached" color="green" style="margin-left: 8px;">缓存结果</a-tag>
      </div>
      <div v-if="aiMeta.surface.length" class="kg-info-row">📌 字面层：{{ aiMeta.surface.join("、") }}</div>
      <div v-if="aiMeta.deep.length" class="kg-info-row">📌 内在层：{{ aiMeta.deep.join("、") }}</div>
      <div v-if="aiMeta.skeleton && aiMeta.skeleton.length" class="kg-info-row">
        <div>🦴 骨架：</div>
        <div v-for="(item, i) in aiMeta.skeleton" :key="i" class="kg-skeleton-item">
          {{ typeof item === 'object' ? item.step : item }}
          <span v-if="item && typeof item === 'object' && item.path_evidence" class="kg-skeleton-evidence">↳ {{ item.path_evidence }}</span>
        </div>
      </div>
    </div>

    <div class="kg-outline-divider">─── 纲目正文 ───</div>

    <!-- 中文纲目 -->
    <transition name="slide-down">
      <div v-if="showAIAnswer" class="ai-answer-card">
        <div class="ai-answer-header">
          <span style="font-weight: bold; color: #667eea;">📝 中文纲目</span>
          <a-button type="text" size="small" @click="copyAiAnswer" class="ai-copy-btn">
            <CheckOutlined v-if="aiAnswerCopied" style="color: #52c41a;" />
            <CopyOutlined v-else />
            {{ aiAnswerCopied ? "已复制" : "复制" }}
          </a-button>
        </div>
        <div class="ai-answer-content" v-html="aiAnswerFormatted"></div>
        <div v-if="aiResult?.answer" class="ai-download-row">
          <span class="ai-download-label">下载格式：</span>
          <a-checkbox-group v-model:value="downloadFormatsZh">
            <a-checkbox value="docx">DOCX</a-checkbox>
            <a-checkbox value="pdf">PDF</a-checkbox>
          </a-checkbox-group>
          <a-button type="primary" size="small" :loading="downloadingZh" :disabled="downloadingZh || downloadFormatsZh.length === 0" @click="downloadFormattedZh">
            <LoadingOutlined v-if="downloadingZh" spin />
            <DownloadOutlined v-else />
            {{ downloadingZh ? "格式化并下载中…" : "刷格式并下载" }}
          </a-button>
        </div>
      </div>
    </transition>

    <!-- 英文纲目 -->
    <div v-if="showAIAnswer && includeEnglishOutline" class="ai-answer-card ai-answer-card-en">
      <div class="ai-answer-header">
        <span style="font-weight: bold; color: #667eea;">📝 英文纲目</span>
        <a-button v-if="answerEn" type="text" size="small" @click="copyAiAnswerEn" class="ai-copy-btn">
          <CheckOutlined v-if="aiAnswerEnCopied" style="color: #52c41a;" />
          <CopyOutlined v-else />
          {{ aiAnswerEnCopied ? "已复制" : "复制" }}
        </a-button>
      </div>
      <div v-if="loadingEnglish" class="ai-answer-content ai-answer-loading-en">
        <a-spin size="small" /> 正在生成英文纲目…
      </div>
      <div v-else-if="errorEnglish" class="ai-answer-content ai-answer-error-en">
        {{ errorEnglish }}
      </div>
      <div v-else-if="answerEn" class="ai-answer-content" v-html="aiAnswerEnFormatted"></div>
      <div v-if="answerEn" class="ai-download-row">
        <span class="ai-download-label">下载格式：</span>
        <a-checkbox-group v-model:value="downloadFormatsEn">
          <a-checkbox value="docx">DOCX</a-checkbox>
          <a-checkbox value="pdf">PDF</a-checkbox>
        </a-checkbox-group>
        <a-button type="primary" size="small" :loading="downloadingEn" :disabled="downloadingEn || downloadFormatsEn.length === 0" @click="downloadFormattedEn">
          <LoadingOutlined v-if="downloadingEn" spin />
          <DownloadOutlined v-else />
          {{ downloadingEn ? "格式化并下载中…" : "刷格式并下载" }}
        </a-button>
      </div>
    </div>

    <!-- 繁体纲目 -->
    <div v-if="showAIAnswer && includeTraditionalOutline" class="ai-answer-card ai-answer-card-zh-tw">
      <div class="ai-answer-header">
        <span style="font-weight: bold; color: #2d5016;">📝 繁体纲目</span>
        <a-button v-if="answerZhTw" type="text" size="small" @click="copyAiAnswerZhTw" class="ai-copy-btn">
          <CheckOutlined v-if="aiAnswerZhTwCopied" style="color: #52c41a;" />
          <CopyOutlined v-else />
          {{ aiAnswerZhTwCopied ? "已复制" : "复制" }}
        </a-button>
      </div>
      <div v-if="loadingTraditional" class="ai-answer-content ai-answer-loading-zh-tw">
        <a-spin size="small" /> 正在生成繁体纲目…
      </div>
      <div v-else-if="errorTraditional" class="ai-answer-content ai-answer-error-zh-tw">
        {{ errorTraditional }}
      </div>
      <div v-else-if="answerZhTw" class="ai-answer-content" v-html="aiAnswerZhTwFormatted"></div>
      <div v-if="answerZhTw" class="ai-download-row">
        <span class="ai-download-label">下载格式：</span>
        <a-checkbox-group v-model:value="downloadFormatsZhTw">
          <a-checkbox value="docx">DOCX</a-checkbox>
          <a-checkbox value="pdf">PDF</a-checkbox>
        </a-checkbox-group>
        <a-button type="primary" size="small" :loading="downloadingZhTw" :disabled="downloadingZhTw || downloadFormatsZhTw.length === 0" @click="downloadFormattedZhTw">
          <LoadingOutlined v-if="downloadingZhTw" spin />
          <DownloadOutlined v-else />
          {{ downloadingZhTw ? "格式化并下载中…" : "刷格式并下载" }}
        </a-button>
      </div>
    </div>

    <!-- 引用来源（可折叠） -->
    <div v-if="aiMeta.mainSources.length > 0" class="ai-sources">
      <div class="ai-sources-header" @click="showAISources = !showAISources" style="cursor: pointer;">
        <span style="font-weight: bold; color: #764ba2;">📚 引用来源 ({{ aiMeta.mainSources.length }} 条) {{ showAISources ? '▼' : '▶' }}</span>
      </div>
      <template v-if="showAISources">
        <a-divider style="margin: 8px 0"></a-divider>
        <div v-for="(src, idx) in aiMeta.mainSources" :key="idx" class="source-item">
          <div class="source-title">
            <span style="font-weight: bold; color: #1677ff;">{{ idx + 1 }}. </span>
            <a-tag :color="getSourceLabel(src.chunk_id).color" size="small" style="margin-right: 6px;">{{ getSourceLabel(src.chunk_id).label }}</a-tag>
            <span>{{ formatSourceTitle(src) }}</span>
          </div>
          <div v-if="src.text_preview && getSourceType(src.chunk_id) !== 'firewall'"
               class="source-content"
               style="color: #666; margin-left: 28px; margin-top: 4px; font-size: 13px; line-height: 1.5;">
            {{ src.text_preview }}
          </div>
        </div>
      </template>
    </div>
    
    <div style="margin-bottom: 360px"></div>
  </div>
  <div v-if="showInfo == 3">
    <a-result status="404" title="没有搜到任何内容，请换个关键字试试" />
  </div>
  <div v-if="showInfo == 4" class="spin">
    <a-spin tip="加载中……" size="large" />
  </div>
  <ShowRes />
</template>

<style scoped>
.spin {
  text-align: center;
}
.up,
.down {
  margin: 5px 0;
}
.space {
  margin-bottom: 3px !important;
}
.tag,
.text_tag,
.tag_footer {
  cursor: pointer;
  font-size: 16px;
}
.tag_footer {
  background-color: #fff0f6;
  color: #8316ff;
  padding: 0 5px;
  border-radius: 5px;
}
.res-title {
  color: #1677ff;
  font-size: 17px;
}
.tag:hover {
  background-color: #8316ff;
  color: #fff;
}
.tag_footer:hover {
  background-color: rgb(245, 66, 96);
  color: #fff;
}
.res {
  border: 1px solid #ccc;
  border-radius: 10px;
  margin-bottom: 10px;
  padding: 5px;
  background-color: white;
}
.textindex {
  color: #fff;
  margin-bottom: 5em;
  text-align: justify;
}
.info {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  margin-top: 20px;
}
.cat {
  width: 80%;
  max-width: 960px;
  background-color: #8316ff;
  border-radius: 10px;
  overflow: hidden;
  padding: 20px;
  margin-bottom: 10px;
  color: #fff;
  font-size: 14px;
}
.paoma {
  width: 80%;
  max-width: 960px;
  background-color: #1677ff;
  border-radius: 10px;
  overflow: hidden;
  padding: 20px;
}
.title {
  color: #1677ff;
  font-weight: bold;
  font-size: 1.2em;
}
.search-box {
  margin-top: 80px;
  display: flex;
  justify-content: center;
}
.search-bar {
  width: 80%;
  max-width: 1000px;
}
.search-result {
  margin: 0 2em;
}
.model {
  margin-top: 5px;
  align-items: center;
}

.ai-panel-brand {
  position: absolute;
  top: 12px;
  right: 16px;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 1px;
  font-style: italic;
  background: linear-gradient(135deg, #5b6af0 0%, #a855f7 50%, #ec4899 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  text-shadow: 0 0 20px rgba(168, 85, 247, 0.15);
  pointer-events: none;
}

.ai-meta-panel {
  position: relative;
  margin-top: 12px;
  padding: 16px;
  border: 1px solid #e6f4ff;
  background: #fafdff;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.08);
}

.ai-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px 16px;
}

.ai-meta-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  color: #333;
}

.ai-meta-field > span {
  font-weight: 600;
  color: #222;
}

.ai-meta-field.full {
  grid-column: 1 / -1;
}

.ai-meta-field input,
.ai-meta-field textarea {
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  transition: border-color 0.2s;
}

.ai-meta-field .ai-burden-textarea {
  resize: vertical;
  min-height: 72px;
}

.ai-meta-field .ai-skeleton-textarea {
  resize: vertical;
}

.ai-meta-field input:focus,
.ai-meta-field textarea:focus {
  outline: none;
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgba(22, 119, 255, 0.1);
}

.ai-nature-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ai-nature-btn {
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #555;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.ai-nature-btn:hover:not(:disabled):not(.active) {
  border-color: #1677ff;
  color: #1677ff;
}

.ai-nature-btn.active {
  background: #1677ff;
  border-color: #1677ff;
  color: #fff;
}

.ai-nature-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-panel-actions {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ai-concept-panel {
  background: #f6f8fc;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  padding: 14px 16px;
}
.ai-concept-hint {
  font-size: 12px;
  color: #888;
  margin-bottom: 10px;
}
.ai-concept-section {
  margin-bottom: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
}
.ai-concept-label {
  font-weight: 600;
  font-size: 13px;
  color: #444;
  white-space: nowrap;
}
.ai-concept-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}
.ai-concept-empty {
  color: #aaa;
  font-size: 12px;
}
.ai-concept-reasoning {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  background: #fff;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid #eee;
  margin-top: 6px;
}
.ai-concept-warn {
  color: #fa541c;
  font-size: 12px;
  margin-top: 4px;
}

.ai-panel-hint {
  font-size: 13px;
  color: #fa8c16;
}

.ai-panel-cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.ai-panel-cta :deep(.ant-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  min-width: 200px;
  padding: 0 32px;
}

.ai-depth-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #555;
}

.ai-meta-panel-enter-active,
.ai-meta-panel-leave-active {
  transition: all 0.2s ease;
}

.ai-meta-panel-enter-from,
.ai-meta-panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.text_tag {
  margin-left: 5px;
  padding: 3px 12px;
}

.text_tag:hover {
  background-color: #1677ff;
  color: #fff;
}
.footer_fix {
  bottom: 0;
  position: fixed;
  width: 100%;
  background-color: #fff;
  border-top: 1px solid #e7e7e7;
  padding: 10px 0;
  text-align: center;
  color: #777;
}

/* AI 问答样式 */
.ai-result {
  margin: 0 2em;
}

/* AI 加载动画容器 */
.ai-loading-container {
  margin: 0 2em;
}

.ai-loading {
  margin: 40px 0;
  display: flex;
  justify-content: center;
}

.ai-result-loading {
  margin-top: 20px;
}

.ai-loading-card {
  background: linear-gradient(135deg, #667eea10 0%, #764ba210 100%);
  border: 2px solid #667eea;
  border-radius: 16px;
  padding: 60px 80px;
  text-align: center;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.2);
  animation: pulse-border 2s ease-in-out infinite;
}

@keyframes pulse-border {
  0%, 100% {
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.2);
  }
  50% {
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.4);
  }
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.custom-spinner {
  display: flex;
  gap: 12px;
  align-items: center;
}

.spinner-dot {
  width: 16px;
  height: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 50%;
  animation: bounce 1.4s ease-in-out infinite;
}

.spinner-dot:nth-child(1) {
  animation-delay: 0s;
}

.spinner-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.spinner-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.2);
    opacity: 1;
  }
}

.loading-text {
  font-size: 20px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: text-glow 2s ease-in-out infinite;
}

@keyframes text-glow {
  0%, 100% {
    opacity: 0.8;
  }
  50% {
    opacity: 1;
  }
}

.loading-tips {
  font-size: 14px;
  color: #666;
  margin-top: -5px;
}

/* 渐进显示过渡效果 */
.fade-slide-enter-active {
  animation: fadeSlideIn 0.6s ease-out;
}

@keyframes fadeSlideIn {
  0% {
    opacity: 0;
    transform: translateY(20px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

/* AI答案从上方滑入效果 */
.slide-down-enter-active {
  animation: slideDownIn 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes slideDownIn {
  0% {
    opacity: 0;
    transform: translateY(-30px) scale(0.95);
  }
  60% {
    opacity: 0.8;
    transform: translateY(5px) scale(1.02);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* 淡入淡出效果 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* AI正在整理答案提示 */
.ai-preparing {
  background: linear-gradient(135deg, #ffeaa710 0%, #ffdd5710 100%);
  border: 2px dashed #f59e0b;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  text-align: center;
}

.preparing-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 16px;
  font-weight: 500;
  color: #d97706;
}

.preparing-spinner {
  display: flex;
  gap: 6px;
}

.preparing-spinner .dot {
  width: 8px;
  height: 8px;
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  border-radius: 50%;
  animation: preparingBounce 1.2s ease-in-out infinite;
}

.preparing-spinner .dot:nth-child(1) {
  animation-delay: 0s;
}

.preparing-spinner .dot:nth-child(2) {
  animation-delay: 0.15s;
}

.preparing-spinner .dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes preparingBounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.3);
    opacity: 1;
  }
}

.ai-answer-card {
  background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
  border: 2px solid #667eea;
  border-radius: 12px;
  padding: 28px 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.ai-answer-header {
  font-size: 18px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(102, 126, 234, 0.3);
}

.ai-copy-btn {
  color: #667eea;
  font-size: 14px;
  background-color: rgba(102, 126, 234, 0.2);
  border-radius: 6px;
  padding: 5px 14px;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.ai-copy-btn:hover {
  color: #764ba2;
  background-color: rgba(118, 75, 162, 0.25);
}

.ai-answer-content {
  line-height: 1.8;
  font-size: 16px;
  color: #333;
  white-space: pre-wrap;
}
.ai-answer-content strong {
  font-weight: 700;
  color: #1a1a2e;
}
.ai-answer-loading-en,
.ai-answer-error-en,
.ai-answer-loading-zh-tw,
.ai-answer-error-zh-tw {
  color: #666;
  padding: 12px 0;
}
.ai-answer-error-en,
.ai-answer-error-zh-tw {
  color: #c41e3a;
}

.ai-download-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(102, 126, 234, 0.3);
}
.ai-download-row .ai-download-label {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}
.ai-download-row .ant-checkbox-group {
  display: inline-flex;
  gap: 8px;
}

.ai-sources {
  background-color: white;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  padding: 15px;
  margin-bottom: 20px;
}

.ai-sources-header {
  font-size: 17px;
  margin-bottom: 5px;
}

.source-item {
  border-left: 3px solid #764ba2;
  padding: 10px 15px;
  margin-bottom: 15px;
  background-color: #fafafa;
  border-radius: 5px;
}

.source-title {
  font-size: 16px;
  margin-bottom: 8px;
  color: #1677ff;
}

.source-content {
  margin: 8px 0;
  line-height: 1.6;
  color: #555;
  font-size: 14px;
}
.source-meta {
  margin-top: 8px;
}

.claude-payload-section {
  margin-top: 20px;
  margin-bottom: 20px;
}

.claude-payload-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.claude-payload-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.claude-payload-label {
  font-weight: 600;
  color: #555;
  font-size: 13px;
}

.claude-payload-pre {
  margin: 0;
  padding: 12px;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

/* KG-RAG 信息栏 */
.kg-info-bar {
  background: linear-gradient(135deg, #f0f5ff 0%, #e6f7ff 100%);
  border: 1px solid #91caff;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.kg-info-stats {
  font-size: 15px;
  color: #333;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.kg-info-stats strong {
  color: #1a1a2e;
}
.kg-info-sep {
  margin-left: 16px;
}
.kg-info-row {
  font-size: 14px;
  color: #444;
  margin-top: 6px;
  line-height: 1.6;
}
.kg-skeleton-item {
  padding-left: 20px;
  font-size: 15px;
  color: #555;
  line-height: 1.7;
}
.kg-skeleton-evidence {
  display: block;
  font-size: 13px;
  color: #6090c0;
  padding-left: 8px;
  line-height: 1.4;
}
.kg-outline-divider {
  text-align: center;
  color: #999;
  font-size: 13px;
  margin: 12px 0 16px;
  letter-spacing: 2px;
}

/* ========== 移动端：768px ========== */
@media (max-width: 768px) {
  .search-box {
    margin-top: 56px;
    padding: 0 12px;
  }
  .search-bar {
    width: 100%;
    max-width: 100%;
  }
  .search-bar .search {
    width: 100%;
    max-width: 100%;
  }
  .search-bar :deep(.ant-input-search),
  .search-bar :deep(.ant-input-group) {
    max-width: 100%;
  }
  .search-result,
  .ai-result,
  .ai-loading-container {
    margin: 0 1em;
  }
  .model {
    margin-top: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .model .ant-radio-group {
    flex-wrap: wrap;
  }
  .model .ant-btn {
    min-height: 40px;
  }
  .cat,
  .paoma {
    width: 95%;
    padding: 14px;
    font-size: 13px;
  }
  .ai-meta-panel {
    padding: 12px;
  }
  .ai-meta-grid {
    grid-template-columns: 1fr;
  }
  .ai-panel-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .ai-panel-cta {
    margin-left: 0;
    flex-direction: column;
    align-items: stretch;
  }
  .ai-panel-cta :deep(.ant-btn) {
    width: 100%;
    min-height: 44px;
  }
  .ai-loading-card {
    padding: 40px 24px;
  }
  .loading-text {
    font-size: 18px;
  }
  .ai-answer-card {
    padding: 20px 14px;
  }
  .ai-answer-content {
    font-size: 15px;
  }
  .source-item {
    padding: 8px 12px;
  }
  .res {
    padding: 8px;
  }
}

/* ========== 移动端：480px ========== */
@media (max-width: 480px) {
  .search-box {
    margin-top: 52px;
    padding: 0 8px;
  }
  .search-bar :deep(.ant-input-group-addon) {
    min-width: 0;
  }
  .search-bar :deep(.ant-select) {
    max-width: 56px;
  }
  .search-result,
  .ai-result,
  .ai-loading-container {
    margin: 0 0.5em;
  }
  .cat,
  .paoma {
    width: 100%;
    padding: 12px;
    font-size: 12px;
  }
  .ai-meta-panel {
    padding: 10px;
  }
  .ai-nature-btn {
    padding: 10px 14px;
    min-height: 44px;
  }
  .ai-loading-card {
    padding: 32px 16px;
  }
  .loading-text {
    font-size: 16px;
  }
  .loading-tips {
    font-size: 13px;
  }
  .ai-answer-header {
    font-size: 16px;
    flex-wrap: wrap;
    gap: 8px;
  }
  .ai-answer-content {
    font-size: 14px;
  }
  .ai-sources-header,
  .source-title {
    font-size: 15px;
  }
  .source-content {
    font-size: 13px;
  }
  .tag,
  .text_tag,
  .tag_footer {
    font-size: 14px;
  }
  .res-title {
    font-size: 15px;
  }
}
</style>
