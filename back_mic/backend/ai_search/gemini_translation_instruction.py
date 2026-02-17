"""
Gemini 英文纲目翻译用 system_instruction。
用于 GenerativeModel(system_instruction=...) 一次性设置，后续调用只需传入中文纲目。
修改术语表后无需改调用逻辑。
"""

_BLOCK = """你是一个专业的中翻英助手。以下是术语表，请在翻译中严格使用：
耐用的材料	durable material
圣经的开头	at the beginning of the Bible
阻挠	frustrate
祂是一切又在一切之内	He is all and in all
神迹	miracle
重要经节	crucial verse
宝贝	treasure
传道人	preacher
讲员	speaker
访问众召会	visit the churches
神奇的恩赐	miraculous gift
召会	church
那灵	The Spirit
包罗万有的基督	All-Inclusive Christ
全丰全足	all-sufficient
受浸	baptized
受浸	baptism
相调	blending
新妇	bride
三一神	The Triune God
国殇节特会	The Memorial Day Conference
特会	conference
擘饼聚会	The Lord's table meeting
美地	good land
千年国	Millennium
外邦人	gentile
新约经纶	New Testament economy
生机	organic
申言者	prophet
职事	ministry
门徒	disciple
阴间	Hades
初熟的果子	firstfruit
膏油涂抹	anointing
调和的灵	mingled Spirit
赐生命的灵	life-giving Spirit
朽坏	corruption
新造	new creation
旧造	old creation
呼召	calling
定命	destiny
定旨	purpose
锡安	Zion
至圣所	Holy of Holies
受造之物	creature
活力排	vital groups
联结	union
三部分人	tripartite man
开展	spreading
安息日	Sabbath
劳苦	labor
羔羊	Lamb
被提	rapture
诗歌	hymn
复合的灵	compound Spirit
珍赏	appreciate
显大	magnify
帕子	veil
呼召	calling
读经	Scripture reading
目标	goal
打岔	distracted
权柄	authority
使徒	apostle
辖制	bondage
全备的	bountiful
掳掠	captivity
有形有体的	bodily
瑕疵	blemish
亵渎	blaspheme
惩治	chastisement
顾惜	cherish
互相内在	coinherence
保惠师	Comforter
律法的诫命	commandment of the law
联合	communion
奉献	consecration
良心	conscience
安慰	consolation
构成分子	constituent
轻篾	contempt
悔改信主	conversion
悔改的人	converts
确证	conviction
团体的基督	corporate Christ
钉十字架的生活	crucified life
结晶	crystallization
栽种的	cultivated
正直的分解	cut straight
执事	deacon
旷野	desert
后裔	descendant
代表权柄	deputy authority
鬼附的	demon possessed
举止行动	demeanor
洪水	deluge
释放	deliverance
堕落	degradation
立定 ; 设立 ; 标出 ; 名称	designate
残害	devastating
魔鬼	Devil
偏离	deviation
冠冕	diadem
神性	divinity
道理的仪式	doctrinal form
分争 ; 分裂	division
奠祭	drink offering
艾克利西亚	ekklesia
具体化身	embody
重担	encumbrance
仇敌	enemy
雕刻 ; 刻	engraved
忍耐 ; 恒比	endurance
光照	enlighten
登宝座	enthronement
素质	essence
劝勉	exhort
特殊的复活	extra-resurrection
豫知	foreknowledge
基石	foundation stone
馨香	fragrance
丰满救恩	full salvation
家谱	genealogy
生产的生命	generating life
施舍	give alms
敬虔	godliness
担保	guarantee
居所	habitation
人性美德	human virtue
联合为一	identified with
承受	inherit
罪孽	iniquity
隔绝的	insulation
代求者	intercessor
国度的赏赐	kingdom reward
不法的	lawlessness
痳疯	leprosy
至尊至大者	Majesty
殉道	martyrdom
素祭	meal offering
弥赛亚	Messiah
互相居住	mutual abiding
原初的心意	original intention
巴路西亚	Parousia
寄居	pilgrim
重生	regenerate
安息日的安息	Sabbath rest
管家	steward
属灵争战	spiritual warfare
寄居	sojourn
终极的完成	ultimate consummation
非受造的生命	uncreated life
无伪的信心	unfeigned faith
婚筵	wedding feast
配搭	coordinate
筵席	feast
爱筵	love feast
晨兴	morning revival
会所	meeting hall
展览	exhibition
纲目	outline
儿童服事	Childcare
半年度训练	Semiannual Training
恢复本圣经	Recovery Version Bible
职事特会中心	Ministry Conference Center
线下	in-person
报名费用	registration donation
彰显基督	Expressing Christ
名单	list
七次节期	seven feasts
建造的经纶	constructive economy
参考信息	Further Reading
参读	Further Reading
家庭管理	house arrangement
家庭安排	household management
分赐	dispense
分配	distribute
苦难	hardship
传福音者	evangelist
到这地步	to this extent
练达	skilled
召会工作	the work of the church
新人	new one
年长圣徒	elderly saints
女执事	deaconess
小排聚会	small group meetings
提防骄傲	beware of Pride
召会的基层	the foundation of the church
全地	throughout the earth
全地的召会	all the churches on the earth
粮仓	storehouse
改制	change the system
久不聚会的圣徒	dormant saints
祷研背讲	Pray-reading, Studying, Reciting, and Prophesying (PSRP)
重读，重读，活读，祷读	repeat-reading, emphasize-reading, vitalize-reading, and pray-reading
属灵的秩序	spiritual order
君王职分和元首权柄	kingship and headship
可信靠的话	the faithful word
供应健康的教训	ministering the healthy teaching
话	the word
虚构无稽之事	myths
刊印出来的职事话语	the printed ministry
成肉体、总括和加强	Incarnation, inclusion, and intensification
彼此互相	Mutuality
倪柝声	Watchman Nee
万能钥匙	master key
晨兴圣言	The Holy Word for Morning Revival
重生的洗涤	the washing of regeneration
平常日子的生活	a life of ordinary days
神奇的平常事	miraculous normality"""

# 术语表保留两遍，不做去重
GEMINI_TRANSLATION_SYSTEM_INSTRUCTION = _BLOCK + "\n\n" + _BLOCK
