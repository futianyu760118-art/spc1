/**
 * 全局搜索 fuzzy 匹配算法（纯函数，独立可测）。
 *
 * 设计：
 *  - 数据源为侧栏已按权限过滤的菜单树（PermissionAwareItem 结构），扁平化取有路由 key 的叶子节点，
 *    因此结果与用户在侧栏实际可见的菜单完全一致（含 MainLayout 注入的 v2 额外页面）。
 *  - 匹配优先级：标题子串 > 路径子串 > 拼音首字母子串 > 标题模糊（字符顺序出现，可不连续）。
 *  - 最近访问命中额外加权 +50，保证常用页面靠前。
 *  - 拼音首字母靠内置紧凑映射，无第三方依赖；未收录字符回退为字符本身（仅影响拼音匹配，不影响标题/路径子串）。
 */

/** 可搜索的菜单项结构（与 MainLayout 的 PermissionAwareItem 结构兼容，只需 key/label/children）。 */
export interface SearchableMenu {
  key: string
  label: string
  children?: SearchableMenu[]
}

export interface SearchPage {
  /** 叶子节点 key（route_path），作为稳定主键 */
  code: string
  /** 页面标题（菜单 label） */
  title: string
  /** 路由路径（菜单 key） */
  routePath: string
  /** 所属分组名（最近一级父菜单 label，便于在结果中显示模块归属） */
  module: string
  /** 标题的拼音首字母串（小写），如 "销售订单" → "xsdd" */
  pinyin: string
}

export interface MatchResult {
  score: number
  /** 标题中命中字符的下标，用于 <mark> 高亮；拼音/路径命中时为空数组 */
  indices: number[]
  /** 命中类型：title | path | pinyin | fuzzy */
  hit: 'title' | 'path' | 'pinyin' | 'fuzzy'
}

export interface ScoredPage {
  page: SearchPage
  score: number
  indices: number[]
  hit: MatchResult['hit']
  isRecent: boolean
  /** 空查询分组渲染时的分组标题 */
  group?: string
}

/**
 * 紧凑拼音首字母映射（仅收录常用汉字，未收录字符回退为字符本身）。
 * 数据为静态查表，不引入第三方 pinyin 库。
 */
const PINYIN_FIRST: Record<string, string> = parsePinyinTable(
  'a=阿啊吖嗄锕', 'ai=艾爱哀碍癌挨矮埃埃哎唉皑蔼氹', 'an=安按暗案岸俺谙揞埯氨庵桉铵鹌鞍',
  'ang=昂仰盎', 'ao=奥澳傲袄拗懊坳嗷岙獒', 'ba=巴把爸吧罢坝拔霸靶芭疤钯粑鲅',
  'bai=白百摆败拜柏佰', 'ban=半办班般版搬伴拌板扮瓣颁斑钣坂', 'bang=帮邦榜膀傍绑棒磅谤镑',
  'bao=报抱包保宝暴爆饱堡薄雹饱孢', 'bei=北倍备被背杯辈悲碑卑惫贝钡惫邶',
  'ben=本奔苯笨夯畚坌', 'beng=崩绷甭蹦迸堋', 'bi=比必笔毕避闭鄙币彼逼鼻彼碧碧蔽',
  'bian=便边变遍辨辩编贬扁鞭卞弁', 'biao=表标彪婊骠飑镖', 'bie=别瘪憋鳖', 'bin=宾彬斌濒滨摈殡',
  'bing=并病兵冰丙柄秉禀', 'bo=波拨博伯泊播勃驳剥薄菠伯钵铂', 'bu=不步部布补捕哺卜埠',
  'ca=擦', 'cai=才采菜财踩裁彩材蔡', 'can=参残餐惨灿仓蚕惭', 'cang=仓沧苍藏舱',
  'cao=操草槽曹糙嘈', 'ce=策测侧厕册', 'ceng=层蹭曾', 'cha=查察差插叉茶岔刹诧茬碴',
  'chai=拆柴豺侪', 'chan=产铲阐掺颤缠蝉馋谗禅', 'chang=长场常厂唱尝偿畅倡昌猖',
  'chao=超抄朝潮吵巢钞剿', 'che=车彻撤扯澈掣', 'chen=陈臣沉辰晨尘趁衬忱棕',
  'cheng=成程城承称呈惩澄逞秤橙', 'chi=吃迟池持尺赤齿翅斥匙痴', 'chong=充冲虫崇宠种重',
  'chou=抽仇臭稠愁丑筹畴踌', 'chu=出处除初厨楚础储矗触搐', 'chuai=揣', 'chuan=川穿传船喘串椽',
  'chuang=创床窗闯疮幢', 'chui=吹垂炊锤捶', 'chun=春纯蠢淳唇', 'chuo=戳辍',
  'ci=此次词刺辞慈瓷磁茨', 'cong=从丛聪匆葱囱', 'cou=凑', 'cu=粗促醋簇蹴',
  'cuan=窜蹿篡', 'cui=催崔翠脆萃淬淬', 'cun=村存寸蹲', 'cuo=错措搓挫磋',
  'da=大打达搭答瘩', 'dai=代带待戴袋逮怠贷岱', 'dan=单但担弹蛋淡诞胆旦丹惮',
  'dang=当党档挡荡档', 'dao=到道倒导刀岛祷稻盗蹈', 'de=的得德锝',
  'deng=等登灯邓凳瞪蹬', 'di=的地第低底弟递抵帝堤滴笛迪狄', 'dian=点电店典奠垫淀颠滇',
  'diao=调掉钓雕吊碉', 'die=跌叠迭蝶碟谍', 'ding=定订顶丁钉叮鼎锭',
  'diu=丢', 'dong=东动懂洞冬董栋', 'dou=都斗豆抖兜陡', 'du=度都独读督毒堵赌杜镀睹',
  'duan=段断短端锻', 'dui=对队堆兑', 'dun=顿吨敦钝盾蹲', 'duo=多夺朵堕舵剁哆',
  'e=饿恶额俄鹅蛾娥厄扼', 'en=恩嗯', 'er=二而尔耳儿饵迩',
  'fa=发法罚乏伐筏阀珐', 'fan=反返烦犯翻凡繁泛饭贩帆樊', 'fang=方放房防访仿纺妨芳',
  'fei=非飞费废肥匪啡沸斐', 'fen=分份粉奋纷坟焚愤芬', 'feng=风封丰峰锋逢缝蜂凤奉枫',
  'fou=否', 'fu=服府父附符浮副负幅符伏扶抚甫斧腐敷',
  'ga=嘎噶', 'gai=改概盖该钙溉', 'gan=干感敢赶甘肝杆柑竿', 'gang=刚岗钢纲港冈罡',
  'gao=高告稿搞膏糕皋', 'ge=个各革格歌哥阁搁戈鸽葛', 'gei=给',
  'gen=根跟', 'geng=更耕梗埂', 'gong=工公共供功攻巩宫龚弓', 'gou=够构购勾沟狗钩苟垢',
  'gu=古故顾骨估股固雇孤姑', 'gua=挂刮瓜寡褂', 'guai=怪乖拐', 'guan=关观管官馆惯冠灌罐',
  'guang=光广逛', 'gui=规贵归轨鬼桂柜圭硅', 'gun=滚棍', 'guo=国过果裹锅郭',
  'ha=哈蛤', 'hai=还海孩害骇', 'han=含韩寒喊汉旱函涵罕', 'hang=行航航杭',
  'hao=好号毫豪耗浩', 'he=和合何河喝贺核荷', 'hei=黑嘿', 'hen=很狠痕恨',
  'heng=横恒哼', 'hong=红宏洪轰弘虹鸿', 'hou=后候厚侯喉吼',
  'hu=和护互户湖呼忽糊壶虎', 'hua=话化花华划画滑', 'huai=坏怀槐徊', 'huan=还换环幻患缓欢焕',
  'huang=黄皇荒慌煌谎磺簧', 'hui=会回灰汇惠挥辉毁悔汇', 'hun=混婚魂浑', 'huo=活火货或祸获',
  'ji=机及级即记计技纪基极集计击急籍寄积奇激几季吉棘', 'jia=加家价假架佳甲嘉颊',
  'jian=见间建件检健减简兼监坚渐键剑践', 'jiang=江将讲奖降蒋匠桨', 'jiao=叫教交较脚角缴骄娇搅',
  'jie=接结阶届节解借介戒截捷竭洁', 'jin=进金近紧禁尽仅今劲晋', 'jing=经精京景警竞惊境静净镜',
  'jiong=窘炯', 'jiu=就久旧酒九救揪纠', 'ju=据局举聚具句巨拒距俱锯剧炬',
  'juan=卷捐圈倦娟', 'jue=决绝觉掘角爵', 'jun=军均君俊菌峻竣', 'ka=卡咖喀', 'kai=开凯慨揩',
  'kan=看砍勘堪刊侃', 'kang=抗康慷慷', 'kao=考靠烤拷', 'ke=可克科客课颗渴刻柯颗咳',
  'ken=肯啃恳', 'keng=坑铿', 'kong=空恐孔控', 'kou=口扣寇', 'ku=苦库哭裤酷枯窟',
  'kua=跨夸垮挎', 'kuai=快块筷', 'kuan=款宽', 'kuang=况矿狂眶筐',
  'kui=亏奎溃馈', 'kun=困昆捆坤', 'kuo=扩括阔', 'la=拉啦腊辣蜡蓝垃',
  'lai=来赖莱', 'lan=蓝兰览栏懒烂拦澜', 'lang=浪朗郎狼朗', 'lao=老劳牢捞烙姥',
  'le=了乐勒', 'lei=类雷累泪垒磊蕾', 'leng=冷棱', 'li=理里立例离利力历厉礼李丽',
  'lian=联连练炼脸廉怜链莲恋', 'liang=两量亮梁凉粮粱', 'liao=料了辽聊疗撩寥', 'lie=列烈劣裂猎咧',
  'lin=林临邻磷淋霖', 'ling=领令灵零龄岭陵铃', 'liu=流留六刘柳瘤', 'long=龙隆笼隆拢聋陇',
  'lou=楼漏搂篓', 'lu=路鲁录露陆炉鹿禄', 'lv=绿铝旅律滤率', 'luan=乱卵滦',
  'lue=略掠', 'lun=论轮伦仑', 'luo=落罗骆洛螺锣', 'ma=马吗妈麻骂码玛',
  'mai=买卖迈麦脉', 'man=满慢漫曼蛮瞒', 'mang=忙茫盲芒', 'mao=毛冒贸茂帽矛',
  'me=么', 'mei=没每美妹煤霉梅媒', 'men=门们闷', 'meng=梦盟蒙猛孟朦',
  'mi=米密迷蜜秘谜糜', 'mian=面棉免绵缅', 'miao=秒苗描瞄妙', 'mie=灭蔑',
  'min=民敏闽', 'ming=明名命鸣铭', 'miu=谬', 'mo=没末莫模磨摩魔沫漠',
  'mou=某谋牟', 'mu=母木目幕慕墓牧姆穆', 'na=那拿哪呐', 'nai=奶耐乃奈',
  'nan=南男难', 'nang=囊', 'nao=脑闹恼挠', 'ne=呢', 'nei=内', 'nen=嫩',
  'neng=能', 'ni=你尼泥拟逆匿', 'nian=年念粘碾', 'niang=娘酿', 'niao=鸟尿',
  'nie=聂涅捏', 'nin=您', 'ning=宁凝拧泞', 'niu=牛纽扭', 'nong=农弄浓',
  'nou=耨', 'nu=努怒奴', 'nv=女', 'nuan=暖', 'nue=虐', 'nuo=挪诺',
  'o=哦噢', 'ou=欧偶呕藕', 'pa=怕爬趴帕', 'pai=排派拍牌徘',
  'pan=判盘盼攀潘', 'pang=旁庞胖磅', 'pao=跑抛炮袍刨', 'pei=配陪赔培佩沛',
  'pen=盆喷', 'peng=朋棚碰彭膨蓬鹏', 'pi=批皮疲啤坯披劈', 'pian=片偏篇骗',
  'piao=票漂飘瓢剽', 'pie=撇', 'pin=品贫聘拼', 'ping=平评瓶凭屏苹萍',
  'po=破颇泼婆迫坡', 'pou=剖', 'pu=普谱浦铺朴扑瀑', 'qi=期其起记气七企奇骑齐旗乞契',
  'qia=卡恰', 'qian=前钱签潜浅遣歉迁千', 'qiang=强枪墙腔抢呛', 'qiao=桥瞧巧悄撬窍',
  'qie=且切窃怯', 'qin=亲秦勤琴钦侵', 'qing=请清情青轻晴庆顷', 'qiong=穷琼',
  'qiu=球求秋丘酋', 'qu=去区取曲趋屈驱渠', 'quan=全权圈劝券泉', 'que=确缺却鹊雀',
  'qun=群裙', 'ran=然燃染', 'rang=让嚷攘', 'rao=饶绕扰', 're=热惹',
  'ren=人任认仁忍韧', 'reng=仍扔', 'ri=日', 'rong=容荣融溶熔绒', 'rou=肉柔揉',
  'ru=如入儒乳辱', 'ruan=软阮', 'rui=锐瑞蕊', 'run=润闰', 'ruo=若弱',
  'sa=撒洒萨', 'sai=赛塞', 'san=三散伞', 'sang=桑丧嗓', 'sao=扫骚嫂梢',
  'se=色塞涩', 'sen=森', 'seng=僧', 'sha=杀沙傻刹纱', 'shai=筛晒',
  'shan=山陕闪善扇删衫珊', 'shang=上商尚伤赏汤', 'shao=少烧绍稍勺韶', 'she=设社射涉舍蛇',
  'shei=谁', 'shen=什身深申神审慎甚伸', 'sheng=生声胜剩省升绳圣盛', 'shi=是时事市使十师实石识史示始世',
  'shou=手收受寿瘦售首授', 'shu=书数树属术署输熟蜀鼠薯', 'shua=刷耍', 'shuai=率摔甩帅',
  'shuan=栓拴', 'shuang=双爽霜', 'shui=水税睡谁', 'shun=顺瞬', 'shuo=说硕烁',
  'si=四思私似死司撕丝', 'song=送松宋颂讼', 'sou=搜艘嗽', 'su=诉素苏速宿塑俗肃',
  'suan=算酸蒜', 'sui=岁虽随碎遂髓', 'sun=孙损笋', 'suo=所锁缩索',
  'ta=他她它塌塔踏', 'tai=台太态泰抬汰', 'tan=谈贪坦摊弹潭探昙', 'tang=堂塘糖躺烫趟唐',
  'tao=套逃讨陶涛掏', 'te=特', 'teng=疼腾藤', 'ti=提题体替梯啼',
  'tian=天田填甜添', 'tiao=条调跳挑', 'tie=贴铁帖', 'ting=听停庭挺厅亭',
  'tong=同通痛统铜桶筒', 'tou=头投透偷', 'tu=图土突涂吐途屠', 'tuan=团湍',
  'tui=退推腿蜕', 'tun=吞屯臀', 'tuo=拖脱托妥驼', 'wa=挖哇蛙娃瓦袜',
  'wai=外歪', 'wan=完万晚弯碗湾顽腕', 'wang=王往网忘望旺亡枉', 'wei=为位未维卫委违围喂威尾',
  'wen=问文温稳吻纹', 'weng=翁嗡', 'wo=我握窝卧沃', 'wu=无五午吴武误悟污屋',
  'xi=系希息西席喜习细吸戏', 'xia=下夏吓峡瑕霞', 'xian=现线先限险闲鲜咸显献', 'xiang=想向项相像象详香乡',
  'xiao=小笑校销晓肖消霄', 'xie=些写谢解协械斜胁卸', 'xin=新心信欣辛薪', 'xing=行兴星型形性姓刑醒',
  'xiong=兄雄凶胸熊', 'xiu=修秀休绣锈羞', 'xu=许须需续序虚绪', 'xuan=选宣悬旋玄轩',
  'xue=学雪血削穴靴', 'xun=寻迅训讯循逊', 'ya=压呀牙押鸭哑亚', 'yan=言眼研严演烟延燕宴岩',
  'yang=样阳央养扬洋痒', 'yao=要药遥腰邀摇尧', 'ye=也业夜叶页野液', 'yi=一以已意义医亿衣依移艺',
  'yin=因银引音印阴姻', 'ying=应营影映英迎硬赢', 'yo=哟', 'yong=用永永勇涌拥',
  'you=有由又油游友右尤幽', 'yu=于予余预与玉余渔语雨', 'yuan=元原远院员袁缘圆', 'yue=月约越跃岳悦',
  'yun=运云允韵晕', 'za=杂砸咋', 'zai=在再载栽宰', 'zan=咱暂赞',
  'zang=脏葬藏', 'zao=早造糟遭灶', 'ze=则责泽择', 'zei=贼', 'zen=怎', 'zeng=增赠曾',
  'zha=炸扎轧闸', 'zhai=宅摘寨债', 'zhan=站战展占沾绽', 'zhang=张章涨丈帐障掌彰',
  'zhao=找照招着赵罩兆', 'zhe=这者着浙折哲', 'zhei=这', 'zhen=真镇阵珍针侦震枕',
  'zheng=整正证争政郑蒸睁', 'zhi=之只制直至知职支志质执值纸', 'zhong=中种重终钟众忠肿',
  'zhou=周州轴宙皱咒', 'zhu=主住注助猪祝驻株竹烛', 'zhua=抓', 'zhuai=拽',
  'zhuan=专转赚砖', 'zhuang=装状壮庄撞', 'zhui=追坠缀', 'zhun=准',
  'zhuo=桌捉拙浊酌', 'zi=子自字资紫滋姊', 'zong=总从综宗纵棕', 'zou=走奏揍',
  'zu=组足族祖租阻', 'zuan=钻纂', 'zui=最罪嘴醉', 'zun=尊遵',
  'zuo=做作左坐昨琢'
)

function parsePinyinTable(...rows: string[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const row of rows) {
    const eq = row.indexOf('=')
    if (eq < 0) continue
    const letter = row.slice(0, eq)
    for (const ch of row.slice(eq + 1)) {
      map[ch] = letter
    }
  }
  return map
}

/** 计算汉字字符串的拼音首字母串（小写）；未收录字符回退为字符本身的小写形式。 */
export function pinyinFirstLetters(input: string): string {
  let out = ''
  for (const ch of input) {
    const hit = PINYIN_FIRST[ch]
    out += hit ? hit : ch.toLowerCase()
  }
  return out
}

/** 扁平化菜单树，取有路由 key（以 / 开头）的叶子节点。父节点的 label 作为子节点的 module 归属。 */
export function flattenPages(items: SearchableMenu[], parentLabel?: string): SearchPage[] {
  const out: SearchPage[] = []
  for (const item of items) {
    if (item.children?.length) {
      out.push(...flattenPages(item.children, item.label))
      continue
    }
    // 叶子节点：key 是路由路径才纳入搜索；父分组节点的 key 是 code（非路由），跳过
    if (item.key.startsWith('/')) {
      out.push({
        code: item.key,
        title: item.label,
        routePath: item.key,
        module: parentLabel || item.label,
        pinyin: pinyinFirstLetters(item.label),
      })
    }
  }
  return out
}

const RECENT_KEY = 'spc_global_search_recent'
const RECENT_MAX = 5

export function getRecentRoutes(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) return arr as string[]
    }
  } catch {
    /* ignore */
  }
  return []
}

export function saveRecentRoutes(list: string[]): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list))
  } catch {
    /* ignore */
  }
}

export function pushRecentRoute(routePath: string): string[] {
  const list = getRecentRoutes().filter((p) => p !== routePath)
  list.unshift(routePath)
  const trimmed = list.slice(0, RECENT_MAX)
  saveRecentRoutes(trimmed)
  return trimmed
}

export function resetRecent(): void {
  try {
    localStorage.removeItem(RECENT_KEY)
  } catch {
    /* ignore */
  }
}

/** 单页 fuzzy 匹配，返回 score=0 表示不命中。 */
export function fuzzyMatch(query: string, page: SearchPage): MatchResult {
  const q = query.trim().toLowerCase()
  if (!q) return { score: 1, indices: [], hit: 'title' }
  const title = page.title.toLowerCase()
  const path = page.routePath.toLowerCase()

  // 1) 标题子串直接命中
  const tIdx = title.indexOf(q)
  if (tIdx >= 0) {
    let score = 30 + q.length * 5
    if (tIdx === 0) score += 20
    const indices: number[] = []
    for (let i = 0; i < q.length; i++) indices.push(tIdx + i)
    return { score, indices, hit: 'title' }
  }

  // 2) 路径子串命中（如 ord 命中 /order/list）
  const pIdx = path.indexOf(q)
  if (pIdx >= 0) {
    return { score: 15 + q.length * 3, indices: [], hit: 'path' }
  }

  // 3) 拼音首字母命中（如 xsdd 命中 销售订单）
  if (page.pinyin) {
    const pp = page.pinyin
    const ppIdx = pp.indexOf(q)
    if (ppIdx >= 0) {
      let score = 20 + q.length * 4
      if (ppIdx === 0) score += 15
      return { score, indices: [], hit: 'pinyin' }
    }
  }

  // 4) 标题模糊匹配（字符顺序出现，可不连续）
  let ti = 0
  const fIndices: number[] = []
  for (let qi = 0; qi < q.length; qi++) {
    let found = false
    while (ti < title.length) {
      if (title.charAt(ti) === q.charAt(qi)) {
        fIndices.push(ti)
        found = true
        ti++
        break
      }
      ti++
    }
    if (!found) return { score: 0, indices: [], hit: 'fuzzy' }
  }
  let consec = 1
  let maxConsec = 1
  for (let k = 1; k < fIndices.length; k++) {
    if (fIndices[k] === fIndices[k - 1] + 1) {
      consec++
      if (consec > maxConsec) maxConsec = consec
    } else {
      consec = 1
    }
  }
  return { score: 5 + q.length * 2 + maxConsec * 4, indices: fIndices, hit: 'fuzzy' }
}

/**
 * 计算应展示的结果集。
 *  - 空查询：最近访问组 + 全部页面按 module 分组（保留 PermNode.sort_order 顺序）。
 *  - 有关键字：扁平按 score 降序，最近访问命中 +50 加权，同分按标题长度升序。
 */
export function searchPages(query: string, pages: SearchPage[], recent: string[]): ScoredPage[] {
  const q = query.trim().toLowerCase()
  const recentSet = new Set(recent)

  if (!q) {
    const recentPages = recent
      .map((rp) => pages.find((p) => p.routePath === rp))
      .filter((p): p is SearchPage => Boolean(p))
    const flat: ScoredPage[] = []
    recentPages.forEach((p) => {
      flat.push({ page: p, score: 0, indices: [], hit: 'title', isRecent: true, group: '最近访问' })
    })
    // 按 module 分组，保留 pages 内顺序
    const modules: string[] = []
    const byModule: Record<string, SearchPage[]> = {}
    for (const p of pages) {
      if (!byModule[p.module]) {
        byModule[p.module] = []
        modules.push(p.module)
      }
      byModule[p.module].push(p)
    }
    modules.forEach((m) => {
      byModule[m].forEach((p) => {
        flat.push({ page: p, score: 0, indices: [], hit: 'title', isRecent: false, group: m })
      })
    })
    return flat
  }

  const matched: ScoredPage[] = []
  for (const p of pages) {
    const m = fuzzyMatch(q, p)
    if (m.score > 0) {
      const isRecent = recentSet.has(p.routePath)
      matched.push({
        page: p,
        score: m.score + (isRecent ? 50 : 0),
        indices: m.indices,
        hit: m.hit,
        isRecent,
      })
    }
  }
  matched.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    return a.page.title.length - b.page.title.length
  })
  return matched
}
