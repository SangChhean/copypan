<script setup>
import { ref, computed, watch } from "vue";
import { storeToRefs } from "pinia";
import { useStore } from "../store/index";
import { PushpinOutlined, CopyOutlined, CheckOutlined } from "@ant-design/icons-vue";
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

// 仅将 AI 回答中的大点（壹、贰、叁/参…拾）整行加粗；「参考与参读资料：」及之后不加粗
const aiAnswerFormatted = computed(() => {
  const raw = aiResult.value?.answer;
  if (!raw) return "";
  const escaped = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withBr = escaped.replace(/\r\n/g, "\n").replace(/\n/g, "<br>");
  // 「参考与参读资料：」及之后不加粗
  const refIdx = withBr.search(/参考与参读资料[：:]/i);
  const toBold = refIdx >= 0 ? withBr.slice(0, refIdx) : withBr;
  const afterRef = refIdx >= 0 ? withBr.slice(refIdx) : "";
  // 只匹配大点：壹、贰、叁/参、肆…拾 整行（纲目后可为 Tab、顿号、全角空格等）
  const big = /(^|<br>)([\s#*]*)((?:壹[、，\u3000\t]|贰[、，\u3000\t]|(?:叁|参)[、，\u3000\t]|肆[、，\u3000\t]|伍[、，\u3000\t]|陆[、，\u3000\t]|柒[、，\u3000\t]|捌[、，\u3000\t]|玖[、，\u3000\t]|拾[、，\u3000\t])[^<]*?)(?=<br>|$)/g;
  const s = toBold.replace(big, "$1$2<strong>$3</strong>");
  return s + afterRef;
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
      if (err.response.status == 401) {
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

// AI 问答功能
const onAISearch = async () => {
  let input = inputVar.value.trim();
  
  if (input == "") {
    status.value = "error";
    placeholder.value = "搜索内容不能为空";
    return;
  }
  
  // 重置状态
  loadingAI.value = true;
  showInfo.value = 6; // 6表示AI正在思考
  aiResult.value = null;
  showAISources.value = false;
  showAIAnswer.value = false;
  aiLoadingText.value = "🤔 AI 正在分析问题...";
  
  try {
    // 模拟进度更新
    setTimeout(() => {
      if (loadingAI.value) {
        aiLoadingText.value = "🔍 正在检索相关内容...";
      }
    }, 800);
    
    setTimeout(() => {
      if (loadingAI.value) {
        aiLoadingText.value = "💡 正在生成答案...";
      }
    }, 1600);
    
    const res = await axios.post("/api/ai_search", {
      question: input,
      max_results: 50,
      depth: aiDepth.value
    });
    
    aiResult.value = res.data;
    
    // API返回后，先显示引用来源，保持loading状态
    showAISources.value = true;
    showAIAnswer.value = false;
    // 保持 showInfo = 6，显示"AI正在整理答案"
    
    // 延迟800ms后，显示AI答案
    setTimeout(() => {
      showInfo.value = 5; // 切换到结果显示状态
      showAIAnswer.value = true;
      
      // 平滑滚动到AI答案位置
      setTimeout(() => {
        const aiAnswerCard = document.querySelector('.ai-answer-card');
        if (aiAnswerCard) {
          aiAnswerCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 100);
    }, 800);
    
  } catch (err) {
    console.error("AI搜索失败:", err);
    tip("AI搜索失败，请稍后重试");
    showInfo.value = 3;
  } finally {
    loadingAI.value = false;
  }
};
</script>

<template>
  <div class="search-box">
    <div class="search-bar">
      <div class="search">
        <a-input-search :disabled="inputDis" v-model:value="inputVar" :status="status" :placeholder="placeholder" enter-button @search="onSearch" @change="onChange" allowClear>
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
        <a-radio-group 
          v-model:value="aiDepth" 
          button-style="solid" 
          style="margin-left: 10px;"
        >
          <a-radio-button value="general">一般</a-radio-button>
          <a-radio-button value="deep">深度</a-radio-button>
        </a-radio-group>
        <a-button 
          type="primary" 
          :loading="loadingAI" 
          @click="onAISearch" 
          style="margin-left: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"
        >
          AI问答
        </a-button>
      </div>
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
    <!-- 如果还没有引用来源，显示加载动画 -->
    <div class="ai-loading" v-if="!showAISources">
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
            <span v-if="aiDepth === 'general'">正在使用一般模式（50条上下文）</span>
            <span v-else>正在使用深度模式（200条上下文）</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- API返回后，显示引用来源 + "AI正在整理答案"提示 -->
    <div class="ai-result-loading" v-if="showAISources && aiResult">
      <a-alert type="info" show-icon>
        <template #message>
          <span style="font-size: 16px">📚 已找到相关内容</span>
        </template>
      </a-alert>
      <a-divider style="margin: 10px 0"></a-divider>
      
      <!-- AI 正在整理答案提示 -->
      <div class="ai-preparing">
        <div class="preparing-content">
          <div class="preparing-spinner">
            <div class="dot"></div>
            <div class="dot"></div>
            <div class="dot"></div>
          </div>
          <span>✨ AI 正在整理答案...</span>
        </div>
      </div>
      
      <!-- 引用来源 -->
      <transition name="fade-slide">
        <div v-if="aiResult.sources && aiResult.sources.length > 0" class="ai-sources">
          <div class="ai-sources-header">
            <span style="font-weight: bold; color: #764ba2;">📚 引用来源 ({{ aiResult.sources.length }} 条)</span>
          </div>
          <a-divider style="margin: 8px 0"></a-divider>
          <div v-for="(source, idx) in aiResult.sources" :key="idx" class="source-item">
            <div class="source-title">
              <span style="color: #1677ff; font-weight: bold;">{{ idx + 1 }}. </span>
              <a-tag v-if="source.type" color="purple" :bordered="false" style="margin-right: 8px;">{{ source.type }}</a-tag>
              <span v-text="source.reference"></span>
              <a-tag v-if="source.score" color="blue" :bordered="false" style="margin-left: 8px; font-size: 11px;">相关度: {{ source.score }}</a-tag>
            </div>
            <div class="source-content" v-if="source.content">
              <span v-html="source.content"></span>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>

  <!-- AI 问答结果显示 -->
  <div class="ai-result" v-if="showInfo == 5 && aiResult">
    <a-alert type="success" show-icon>
      <template #message>
        <span style="font-size: 16px">✨ AI 智能问答结果</span>
      </template>
    </a-alert>
    <a-divider style="margin: 10px 0"></a-divider>
    
    <!-- AI 答案卡片（从上方滑入） -->
    <transition name="slide-down">
      <div v-if="showAIAnswer" class="ai-answer-card">
        <div class="ai-answer-header">
          <span style="font-weight: bold; color: #667eea;">📝 AI 回答</span>
        </div>
        <a-divider style="margin: 8px 0"></a-divider>
        <div class="ai-answer-content" v-html="aiAnswerFormatted"></div>
      </div>
    </transition>
    
    <!-- 引用来源 -->
    <div v-if="aiResult.sources && aiResult.sources.length > 0" class="ai-sources">
      <div class="ai-sources-header">
        <span style="font-weight: bold; color: #764ba2;">📚 引用来源 ({{ aiResult.sources.length }} 条)</span>
      </div>
      <a-divider style="margin: 8px 0"></a-divider>
      <div v-for="(source, idx) in aiResult.sources" :key="idx" class="source-item">
        <div class="source-title">
          <span style="color: #1677ff; font-weight: bold;">{{ idx + 1 }}. </span>
          <a-tag v-if="source.type" color="purple" :bordered="false" style="margin-right: 8px;">{{ source.type }}</a-tag>
          <span v-text="source.reference"></span>
          <a-tag v-if="source.score" color="blue" :bordered="false" style="margin-left: 8px; font-size: 11px;">相关度: {{ source.score }}</a-tag>
        </div>
        <div class="source-content" v-if="source.content">
          <span v-html="source.content"></span>
        </div>
      </div>
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
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.ai-answer-header {
  font-size: 18px;
  margin-bottom: 5px;
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
</style>
