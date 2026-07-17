<template>
  <div class="ms-root">
    <div class="cn-page-head">
      <button type="button" class="cn-back" @click="router.push('/')">‹‹ 返回</button>
      <span class="cn-page-title">职事信息搜寻</span>
    </div>

    <div class="ms-content">
      <!-- 主分类 -->
      <div class="ms-cats">
        <button
          v-for="item in mainCats"
          :key="item.val"
          type="button"
          class="ms-cat-btn"
          :class="{ active: selectedIndex === item.val }"
          @click="onSelectIndex(item.val)"
        >
          {{ item.lab }}
        </button>
      </div>

      <!-- 搜索栏 -->
      <div class="ms-search-bar">
        <div class="ms-search-row">
          <a-select
            v-if="selectedIndex === '0'"
            v-model:value="selVar1"
            class="ms-select"
            :options="showCatsOne"
            :field-names="{ label: 'lab', value: 'val' }"
            style="width: 72px"
          />
          <a-select
            v-model:value="selVar2"
            class="ms-select"
            :options="showCats"
            :field-names="{ label: 'lab', value: 'val' }"
            style="width: 88px"
          />
          <a-input-search
            v-model:value="inputVar"
            class="ms-input"
            :placeholder="placeholder"
            :status="status"
            :disabled="inputDis"
            enter-button="搜索"
            allow-clear
            @search="onSearch"
            @change="onInputChange"
          />
        </div>
        <div class="ms-mode-row">
          <a-radio-group v-model:value="searchCat" button-style="solid" size="small">
            <a-radio-button v-for="item in matchModes" :key="item.val" :value="item.val">
              {{ item.lab }}
            </a-radio-button>
          </a-radio-group>
        </div>
      </div>

      <!-- 下载离线版 -->
      <div class="ms-offline">
        <div class="ms-offline-text">
          <strong>下载离线版</strong>
          <span>可在无网络环境下本地搜索职事信息（约 966MB）</span>
        </div>
        <a-button type="primary" :loading="offlineDownloading" @click="onDownloadOffline">
          下载离线版
        </a-button>
      </div>

      <!-- 首屏：分类说明 + 轮播卡片（搜索后隐藏） -->
      <div v-if="viewState === 'welcome'" class="ms-welcome">
        <div class="ms-cat-info">
          <div>A类：经文、注解、生命读经、倪文集、李文集、其他</div>
          <div>B类：A类、诗歌、节期纲目</div>
        </div>
        <div class="ms-carousel-box">
          <a-carousel autoplay>
            <div
              v-for="(item, i) in indexshow"
              :key="i"
              class="ms-carousel-item"
              v-html="item"
            ></div>
          </a-carousel>
        </div>
      </div>

      <!-- 加载 -->
      <div v-else-if="viewState === 'loading'" class="ms-loading">
        <a-spin size="large" />
        <span>正在搜索…</span>
      </div>

      <!-- 空结果 -->
      <div v-else-if="viewState === 'empty'" class="ms-empty">
        未找到相关结果，请尝试其他关键词或分类
      </div>

      <!-- 结果列表 -->
      <div v-else-if="viewState === 'results'" class="ms-results">
        <div class="ms-total">
          共搜索到 <em>{{ total }}</em> 条
        </div>

        <div v-for="item in results" :key="item.id" class="ms-card">
          <div class="ms-card-tags">
            <button
              v-for="tag in displayTags(item.tags)"
              :key="tag[0] + tag[1]"
              type="button"
              class="ms-tag"
              @click="openReading(tag[1])"
            >
              {{ tag[0] }}
            </button>
          </div>
          <div class="ms-card-title">{{ item.title }}</div>
          <div v-if="item.up" class="ms-card-up" v-html="item.up"></div>
          <div v-if="item.down" class="ms-card-down" v-html="item.down"></div>
          <div v-if="item.source?.length" class="ms-card-source">
            <span v-for="(s, i) in item.source" :key="i">{{ s }}</span>
          </div>
        </div>

        <div class="ms-pages">
          <a-pagination
            v-model:current="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-size-options="pageSizeOptions"
            size="small"
            show-size-changer
            show-quick-jumper
            @change="onPageChange"
            @showSizeChange="onPageChange"
          />
        </div>
      </div>
    </div>

    <!-- 阅读原文弹窗 -->
    <a-modal
      v-model:open="readingOpen"
      width="100%"
      wrap-class-name="ms-reading-modal"
      :footer="null"
      :destroy-on-close="true"
      @cancel="closeReading"
    >
      <template #title>
        <span class="ms-reading-title">阅读原文</span>
      </template>

      <div v-if="readingLoading" class="ms-loading">
        <a-spin />
        <span>加载中…</span>
      </div>
      <div v-else-if="readingError" class="ms-empty">{{ readingError }}</div>
      <div v-else-if="showData" class="ms-reading-body">
        <a-breadcrumb class="ms-breadcrumb">
          <a-breadcrumb-item v-for="(b, i) in showData.bread || []" :key="i">
            <a v-if="b.refid" @click="openReading(b.refid)">{{ b.text }}</a>
            <span v-else>{{ b.text }}</span>
          </a-breadcrumb-item>
        </a-breadcrumb>

        <div v-if="showData.showButtons == '1'" class="ms-reading-actions">
          <a-button
            size="small"
            :type="isHeading ? 'default' : 'primary'"
            @click="isHeading = false"
          >查看整篇</a-button>
          <a-button
            size="small"
            :type="isHeading ? 'primary' : 'default'"
            @click="isHeading = true"
          >只看标题</a-button>
        </div>

        <a-divider style="margin: 12px 0" />

        <div v-if="showData.cells" class="ms-cells">
          <a-button
            v-for="(c, i) in showData.cells"
            :key="i"
            type="primary"
            @click="openReading(c.refid)"
          >{{ c.text }}</a-button>
        </div>
        <div v-else-if="showData.toc" class="ms-toc">
          <div
            v-for="(t, i) in showData.toc"
            :key="i"
            :class="['ms-toc-item', t.type]"
            v-html="hiLight(t.text)"
            @click="openReading(t.refid)"
          ></div>
        </div>
        <div v-else>
          <div v-if="hideEng" class="ms-only-zh">
            <div
              v-for="(line, i) in showData.zh || []"
              :key="i"
              :class="line[1]"
              v-html="hiLight(line[0])"
            ></div>
          </div>
          <div v-else class="ms-bilingual">
            <div class="ms-col">
              <div
                v-for="(line, i) in showData.zh || []"
                :key="'zh-' + i"
                :class="line[1]"
                v-html="hiLight(line[0])"
              ></div>
            </div>
            <div class="ms-col">
              <div
                v-for="(line, i) in showData.en || []"
                :key="'en-' + i"
                :class="line[1]"
                v-html="hiLight(line[0])"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import http from '@/utils/http.js'
import { authHeaders, getToken } from '@/utils/auth.js'

const router = useRouter()

const mainCats = [
  { lab: '全部', val: '0' },
  { lab: '圣经', val: '1' },
  { lab: '生命读经', val: '2' },
  { lab: '倪文集', val: '3' },
  { lab: '李文集', val: '4' },
  { lab: '其他', val: '5' },
  { lab: '诗歌', val: '6' },
  { lab: '节期纲目', val: '7' },
]

const catLabels = {
  a: '全部',
  b: '书名',
  c: '总题',
  d: '篇题',
  e: '标题',
  f: '大纲',
  g: '摘录',
  h: '大本',
  i: '经文',
  j: '注解',
  k: '系列',
  l: '纲目',
  m: '禁用',
}

const matchModes = [
  { lab: '模糊', val: 'a' },
  { lab: '平衡', val: 'b' },
  { lab: '精确', val: 'c' },
]

const showCatsOne = [
  { lab: 'A类', val: 'a' },
  { lab: 'B类', val: 'b' },
]

// 首屏轮播引文，与离线版 Search.vue 的 indexshow 完全一致
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
]

const selectedIndex = ref('0')
const selVar1 = ref('a')
const selVar2 = ref('a')
const searchCat = ref('a')
const inputVar = ref('')
const status = ref('')
const placeholder = ref('输入搜索内容')
const inputDis = ref(false)

const viewState = ref('welcome') // welcome | loading | results | empty
const results = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const pageSizeOptions = ['10', '20', '30', '40', '50']
const hilights = ref([])

const readingOpen = ref(false)
const readingLoading = ref(false)
const readingError = ref('')
const readingSource = ref(null)
const offlineDownloading = ref(false)
const isHeading = ref(false)
const hideEng = ref(false)
const currentRefid = ref('')

function getCats(keys) {
  return keys.split('').map((k) => ({ lab: catLabels[k] || k, val: k }))
}

const showCats = computed(() => {
  const idx = selectedIndex.value
  let keys = 'm'
  if (idx === '0') keys = 'abde'
  else if (idx === '1') keys = 'ij'
  else if (idx === '2') keys = 'ade'
  else if (idx === '3') keys = 'abde'
  else if (idx === '4') keys = 'abde'
  else if (idx === '5') keys = 'ade'
  else if (idx === '6') keys = 'h'
  else if (idx === '7') keys = 'acdf'
  return getCats(keys)
})

watch(showCats, (arr) => {
  if (arr.length && !arr.some((x) => x.val === selVar2.value)) {
    selVar2.value = arr[0].val
  }
}, { immediate: true })

watch(selVar2, (v) => {
  inputDis.value = v === 'm'
})

function onSelectIndex(val) {
  selectedIndex.value = val
  currentPage.value = 1
  if (inputVar.value.trim()) onSearch()
}

function onInputChange() {
  status.value = ''
  placeholder.value = '输入搜索内容'
  // 清空搜索框时回到首屏展示区（对应原版 showInfo = 1 的初始状态）
  if (!inputVar.value.trim() && viewState.value !== 'loading') {
    viewState.value = 'welcome'
    results.value = []
    total.value = 0
    currentPage.value = 1
  }
}

function buildArgs() {
  const cat1 = selectedIndex.value === '0' ? selVar1.value : selectedIndex.value
  return `${cat1}-${selVar2.value}-${searchCat.value}-${currentPage.value}-${pageSize.value}`
}

async function onSearch() {
  const input = inputVar.value.trim()
  if (!input) {
    status.value = 'error'
    placeholder.value = '搜索内容不能为空'
    return
  }
  if (selVar2.value === 'm') {
    viewState.value = 'empty'
    return
  }

  hilights.value = input.split(/ +/g).filter(Boolean)
  viewState.value = 'loading'

  const form = new FormData()
  form.append('input', input)
  form.append('args', buildArgs())

  try {
    const res = await http.post('/api/cn/es_search/search', form)
    const data = res.data || {}
    total.value = data.total || 0
    results.value = Array.isArray(data.msg) ? data.msg : []
    viewState.value = total.value === 0 ? 'empty' : 'results'
  } catch (e) {
    if (e?.response?.status === 401) {
      router.push('/login')
      return
    }
    message.error(e?.response?.data?.detail || '搜索失败，请稍后重试')
    viewState.value = 'empty'
  }
}

function onPageChange() {
  if (inputVar.value.trim()) onSearch()
}

/** 下载离线包：鉴权方式与资料下载一致（Bearer + fetch） */
async function onDownloadOffline() {
  if (!getToken()) {
    router.push('/login')
    return
  }
  offlineDownloading.value = true
  try {
    const res = await fetch('/api/cn/es_search/download_offline_package', {
      headers: { ...authHeaders() },
    })
    if (res.status === 401) {
      router.push('/login')
      return
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(
        typeof err.detail === 'string' ? err.detail : `下载失败（HTTP ${res.status}）`,
      )
    }
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename\*=UTF-8''([^;\s]+)|filename="?([^";]+)"?/i)
    const filename = match
      ? decodeURIComponent((match[1] || match[2] || '').replace(/['"]/g, '').trim())
      : 'ES7-offline-search.zip'

    // 大文件优先流式写入磁盘，避免整包进内存；不支持时回退 blob（与资料下载一致）
    if (typeof window.showSaveFilePicker === 'function' && res.body) {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [
          {
            description: 'ZIP archive',
            accept: { 'application/zip': ['.zip'] },
          },
        ],
      })
      const writable = await handle.createWritable()
      await res.body.pipeTo(writable)
      message.success('下载完成')
      return
    }

    const blob = await res.blob()
    if (!blob.size) {
      message.warning('未收到文件内容')
      return
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    if (e?.name === 'AbortError') return
    message.error(e?.message || '下载失败')
  } finally {
    offlineDownloading.value = false
  }
}

/** 直接使用后端返回的 tags；不要用搜索结果自身的 id */
function displayTags(tags) {
  if (!Array.isArray(tags) || !tags.length) return []
  return tags.filter((t) => Array.isArray(t) && t.length >= 2 && t[1] && !String(t[1]).includes('outline'))
}

function closeReading() {
  readingOpen.value = false
  readingSource.value = null
  readingError.value = ''
  currentRefid.value = ''
}

/**
 * 打开阅读原文：必须使用 tags 里的 refid（如 cwwn_1-1#0），
 * 不能用搜索命中文档的 id（如 cwwn_1-1#0-7）。
 */
async function openReading(refidRaw) {
  if (!refidRaw) return
  let refid = String(refidRaw)
  let headingOnly = false

  if (refid.includes('outline')) {
    message.info('大纲视图暂未提供，请使用「查看整篇」或「只看标题」')
    return
  }
  if (refid.includes('heading')) {
    refid = refid.replace('-heading', '')
    headingOnly = true
  }

  currentRefid.value = refid
  isHeading.value = headingOnly
  readingOpen.value = true
  readingLoading.value = true
  readingError.value = ''
  readingSource.value = null

  const form = new FormData()
  form.append('refid', refid)

  try {
    const res = await http.post('/api/cn/es_search/reading', form)
    const src = res.data?._source
    if (!src) {
      readingError.value = '原文不存在或暂不可用'
      return
    }
    readingSource.value = src
    hideEng.value = !src.en
    await nextTick()
    const el = document.querySelector('.ms-reading-modal .ant-modal-body')
    if (el) el.scrollTop = 0
  } catch (e) {
    if (e?.response?.status === 401) {
      router.push('/login')
      return
    }
    readingError.value = e?.response?.data?.detail || '加载原文失败'
  } finally {
    readingLoading.value = false
  }
}

const HEADING_TYPES = ['heading', 'ot1', 'bible_reading', 'b_read', 'title', 'bookname']

const showData = computed(() => {
  const res = readingSource.value
  if (!res) return null
  if (!isHeading.value) return res

  const en = res.en || []
  const zh = res.zh || []
  return {
    en: en.filter((item) => HEADING_TYPES.includes(item[1])),
    zh: zh.filter((item) => HEADING_TYPES.includes(item[1])),
    type: res.type,
    refid: res.refid,
    bread: res.bread,
    showButtons: res.showButtons,
    cells: res.cells,
    toc: res.toc,
  }
})

function hiLight(text) {
  if (!text) return ''
  let out = String(text)
  hilights.value.forEach((kw) => {
    if (!kw) return
    out = out.split(kw).join(`<em>${kw}</em>`)
  })
  return out
}
</script>

<style scoped>
.ms-root {
  min-height: 100vh;
  background: #fff;
}

.ms-content {
  max-width: var(--cn-content-max-width, 860px);
  margin: 0 auto;
  padding: 16px 16px 48px;
}

.ms-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.ms-cat-btn {
  border: 1px solid var(--cn-border, #cce4f5);
  background: #fff;
  color: var(--cn-text-secondary, #4a6a84);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.ms-cat-btn:hover {
  border-color: #1b6ca8;
  color: #1b6ca8;
}
.ms-cat-btn.active {
  background: #1b6ca8;
  border-color: #1b6ca8;
  color: #fff;
}

.ms-search-bar {
  background: #ebf4fb;
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 14px;
}

.ms-search-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ms-input {
  flex: 1;
  min-width: 0;
}

.ms-mode-row {
  margin-top: 10px;
}

.ms-offline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px dashed var(--cn-border, #cce4f5);
  border-radius: 8px;
  margin-bottom: 20px;
  background: #fff;
}
.ms-offline-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: var(--cn-text-secondary, #4a6a84);
}
.ms-offline-text strong {
  color: #1b6ca8;
  font-size: 14px;
}

.ms-welcome {
  padding: 24px 0 40px;
}
.ms-cat-info {
  background: #ebf4fb;
  border: 1px solid rgba(27, 108, 168, 0.15);
  border-radius: 10px;
  padding: 16px 20px;
  color: var(--cn-text-secondary, #4a6a84);
  font-size: 14px;
  line-height: 2;
}
.ms-carousel-box {
  margin-top: 20px;
  background: #ebf4fb;
  border: 1px solid rgba(27, 108, 168, 0.15);
  border-radius: 10px;
  padding: 20px 24px 36px;
}
.ms-carousel-item {
  color: var(--cn-text-secondary, #4a6a84);
  font-size: 14px;
  line-height: 1.9;
  text-align: justify;
  padding: 4px 8px 12px;
  min-height: 120px;
}
/* 轮播指示点改为蓝色主题（默认白色在浅色背景上不可见） */
.ms-carousel-box :deep(.slick-dots li button) {
  background: #1b6ca8;
  opacity: 0.3;
}
.ms-carousel-box :deep(.slick-dots li.slick-active button) {
  background: #1b6ca8;
  opacity: 1;
}

.ms-loading,
.ms-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 12px;
  color: var(--cn-text-secondary, #4a6a84);
}

.ms-total {
  margin-bottom: 12px;
  font-size: 15px;
  color: var(--cn-text-primary, #1a2a3a);
}
.ms-total em {
  color: #1b6ca8;
  font-style: normal;
  font-weight: 700;
  font-size: 18px;
}

.ms-card {
  background: #ebf4fb;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.ms-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.ms-tag {
  border: none;
  background: #1b6ca8;
  color: #fff;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
}
.ms-tag:hover {
  opacity: 0.9;
}
.ms-card-title {
  font-weight: 600;
  color: #1a2a3a;
  margin-bottom: 8px;
}
.ms-card-up :deep(em),
.ms-card-down :deep(em) {
  background: #ffe58f;
  font-style: normal;
  padding: 0 1px;
}
.ms-card-up,
.ms-card-down {
  font-size: 14px;
  line-height: 1.7;
  color: #1a2a3a;
  margin-bottom: 6px;
}
.ms-card-source {
  margin-top: 8px;
  font-size: 12px;
  color: var(--cn-text-muted, #94a3b8);
}
.ms-card-source span {
  display: block;
}

.ms-pages {
  margin-top: 20px;
  text-align: center;
}

.ms-reading-title {
  color: #1b6ca8;
  font-weight: 600;
}
.ms-reading-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.ms-cells {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ms-toc-item {
  cursor: pointer;
  padding: 8px 10px;
  background: #ebf4fb;
  border-radius: 6px;
  margin-bottom: 6px;
}
.ms-toc-item:hover {
  background: #1b6ca8;
  color: #fff;
}
.ms-only-zh,
.ms-col {
  background: #f5f9fc;
  padding: 12px;
  border-radius: 8px;
}
.ms-bilingual {
  display: flex;
  gap: 16px;
}
.ms-bilingual .ms-col {
  flex: 1;
  min-width: 0;
}
.ms-reading-body :deep(em) {
  background: #ffe58f;
  font-style: normal;
}
.ms-reading-body :deep(.ver),
.ms-reading-body :deep(.text) {
  text-align: justify;
  padding: 6px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 6px;
}
.ms-reading-body :deep(.bookname) {
  text-align: center;
  font-weight: bold;
  font-size: x-large;
  color: #0b6108;
}
.ms-reading-body :deep(.title) {
  color: #1b6ca8;
  font-weight: bold;
  font-size: large;
  text-align: center;
  margin-bottom: 1em;
}
.ms-reading-body :deep(.heading) {
  color: #1b6ca8;
  font-weight: bold;
  text-align: center;
}
.ms-reading-body :deep(.ot1) {
  font-weight: bold;
  font-size: large;
}

@media (max-width: 640px) {
  .ms-search-row {
    flex-wrap: wrap;
  }
  .ms-input {
    width: 100%;
    flex: auto;
  }
  .ms-offline {
    flex-direction: column;
    align-items: flex-start;
  }
  .ms-bilingual {
    flex-direction: column;
  }
}
</style>

<style>
.ms-reading-modal .ant-modal {
  max-width: 100%;
  top: 0;
  padding-bottom: 0;
  margin: 0;
}
.ms-reading-modal .ant-modal-content {
  min-height: 80vh;
}
.ms-reading-modal .ant-modal-body {
  max-height: calc(100vh - 110px);
  overflow-y: auto;
}
</style>
