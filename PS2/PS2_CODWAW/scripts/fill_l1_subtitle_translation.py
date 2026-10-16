"""Fill Chinese translations for the L1_Gcan subtitle table (whisper_results.json).

Keys of the translation table are the ASR text (case/space insensitive).
The script only writes `translation` and `note`; `asr_text`, the key order and
the file format (no BOM, LF, 2-space indent) are preserved.

Usage:
  python fill_l1_subtitle_translation.py [--json PATH] [--report PATH] [--dry]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(r'C:\TRANSLATE\TEMP\COLDFEAR\PS2CODWAW')
DEF_JSON = ROOT / 'SOUND' / 'subtitles' / 'L1_Gcan_am' / 'whisper_results.json'
DEF_REPORT = ROOT / 'SOUND' / 'subtitles' / 'L1_Gcan_am' / 'asr' / 'translation_review.tsv'
NOTE = '译文已填；ASR 识别未听音校对。'

T = {
    # ---- generic US combat barks -------------------------------------------
    "GRENADE!": "手雷！",
    "GRENADE GET DOWN!": "手雷，趴下！",
    "GET OUTTA HERE!": "快离开那儿！",
    "GET AWAY FROM IT!": "离它远点！",
    "HIT THE DECK!": "卧倒！",
    "FIRE IN THE HOLE!": "要炸了！",
    "GRENADE GOING IN!": "手雷进去了！",
    "Grenade going in!": "手雷进去了！",
    "Throw in grenade! Get back, fellas!": "扔手雷进去！退后，伙计们！",
    "I'm pulling the pin, look out!": "我拔销了，小心！",
    "WATCH IT! LIVE GRENADE!": "小心！手雷要炸了！",
    "THIS'LL WAKE EM UP!": "这下够他们清醒的！",
    "There you go!": "好样的！",
    "Hoo-ha!": "呼哈！",
    "Hoo-wee!": "喔呼！",
    "THAT'S THE WAY YOU DO IT!": "就该这么打！",
    "NICE ONE!": "漂亮！",
    "MEDEK!": "卫生员！",
    "GET A MEDIC OVER HERE!": "卫生员！这边！",
    "Doc! Where's Doc?!": "军医！军医在哪？！",
    "THEY GOT ME!": "我中弹了！",
    "YEAH I'M HIT!": "是，我中弹了！",
    "RELOADING!": "换弹！",
    "Reloading!": "换弹！",
    "GET DOWN!": "趴下！",
    "FIND SOME COVER!": "找掩体！",
    "TAKE COVER!": "隐蔽！",
    "ХИТ-АНТАК!": "卧倒！",
    "GET YOUR HEAD DOWN!": "低头！",
    "Come on!": "快点！",
    "What's the holdup?": "磨蹭什么呢？",
    "KEEP IT MOVING!": "继续走！",
    "KEEP IT MOVIN'!": "继续走！",
    "STRAIGHT AHEAD!": "正前方！",
    "THIS WAY!": "这边！",
    "AHEAD! MOVE MOVE MOVE!": "前进！走！走！走！",
    "NOW!": "就现在！",
    "POUR IT ON EM BOYS!": "使劲招呼他们，弟兄们！",
    "PIN HIM DOWN!": "压住他！",
    "Target those positions!": "瞄准那些阵地！",
    "FIRE ON THOSE BASTARDS!": "朝那帮狗杂种开火！",
    "TAKE EM DOWN!": "干掉他们！",
    "WE'RE GETTING OUR ASSES HANDED TO US!": "我们被打得满地找牙！",
    "WHERE'S THAT FIRE COMING FROM?!": "火力从哪来的？！",
    "WE'RE GETTING SLAUGHTERED OVER HERE!": "我们这边要被屠光了！",
    "WE COULD USE A LITTLE HELP!": "这边需要支援！",
    "THEY GOT US ZEROED!": "他们锁定我们了！",
    "Bastards are everywhere!": "这帮狗杂种到处都是！",
    "TO NUKA BONSAI!": "天皇陛下万岁！",
    "外 MARTAN": "万岁！",
    "AAAAAAAAAAAAAAAAAAAAH!": "啊啊啊啊啊啊啊——",
    "AHHHHHHHHHH!!!!": "啊啊啊啊啊啊——！！",
    "GRENADE TAKE COVER!": "手雷，隐蔽！",
    "DAMMIT! GRENADE!": "该死！手雷！",
    "GRENADE, LOOK OUT!": "手雷，小心！",
    "MOVE!": "走！",
    "GO!": "走！",
    "GRENADE GO IT IN!": "手雷进去了！",
    "Stand back, I'm throwing it!": "退后，我扔了！",
    "You're back boys! Pineapple going in!": "你们可算回来了！菠萝进去了！",
    "WATCH IT!": "小心！",
    "WATCH YOUR TOES, BOYS!": "脚底下小心，弟兄们！",
    "YEAH!": "好！",
    "ALRIGHT!": "好！",
    "FINALLY!": "总算！",
    "OKAY!": "好！",
    "Right on target!": "正中目标！",
    "GOOD SHOT!": "打得好！",
    "MEDIC!": "卫生员！",
    "MEDIC UP FRONT! MEDIC UP FRONT!": "前面要卫生员！前面要卫生员！",
    "GET SOME MORPHINE UP HERE!": "快拿吗啡上来！",
    "GET HIM OUT OF THERE!": "把他拖出来！",
    "HELP ME CARRY HIM!": "帮我抬他！",
    "Where's Doc?!": "军医在哪？！",
    "TAKING FIRE! FIND COVER!": "遭到射击！找掩体！",
    "GET OUTTA THERE!": "快从那儿撤出来！",
    "GET OUT OF THERE!": "快撤出来！",
    "HIT THE DICK!": "趴下！",
    "GET OUT OF THE OPEN!": "别站在空地上！",
    "Move forward!": "向前推进！",
    "DOUBLE TIME!": "跑步前进！",
    "FORWARD MEN!": "前进，弟兄们！",
    "Come on, man!": "快点，老兄！",
    "SUPPRESSING FIRE!": "火力压制！",
    "GO! START FIRING!": "打！开火！",
    "FIRE!": "开火！",
    "DON'T LET UP!": "别停！",
    "CONCENTRATE YOUR FIRE!": "集中火力！",
    "LOOK OUT!": "小心！",
    "HIT THE DIRT!": "趴下！",
    "ENEMY GRENADE!": "敌人手雷！",
    "WATCH YOURSELF!": "当心！",
    "GET BACK!": "退后！",
    "Hold on a sec!": "等一下！",
    "H้ Lu": "小心！手雷！",
    "THAT DID IT!": "干掉了！",
    "BOOM!": "轰！",
    "DIRECT HIT!": "正中目标！",
    "NICE SHOT!": "好枪法！",
    "Way to go!": "干得好！",
    "Good going!": "干得好！",
    "WHERE'S THE MEDIC?!": "卫生员呢？！",
    "HE'S HIT!": "他中弹了！",
    "I need some help over here!": "这边来个人帮忙！",
    "I'VE GOT A MAN DOWN!": "我这儿有人倒了！",
    "WE NEED A TURNICATE!": "需要止血带！",
    "MOVE UP!": "前进！",
    "STOP FALLING BEHIND!": "别掉队！",
    "COME ON!": "快点！",
    "YOU'RE SLOWING ME DOWN!": "你拖我后腿！",
    "JUST KEEP GOING!": "继续走！",
    "FIRE! NOW!": "开火！就现在！",
    "SHOOT EM MARINES!": "打，弟兄们！",
    "HIT EM HARD!": "狠狠打！",
    "GET THAT FIRE ON THE RIGHT FLANK!": "火力调到右翼！",
    "SHOOT THE BASTARDS!": "打死这帮狗杂种！",
    "TAKING FIRE!": "遭到射击！",
    "Get behind something!": "找个东西躲后面！",
    "WHERE THE HELL ARE THEY?!": "他们到底在哪？！",
    "WHERE THE HELL DID THEY COME FROM?!": "这帮家伙到底从哪冒出来的？！",
    "THEY'VE GOT US OUTNUMBERED!": "他们人比我们多！",
    "THERE'S TOO MANY OF THEM!": "他们人太多了！",
    "JAPANESE GRENADE! RUN!": "鬼子手雷！跑！",
    "GET THE HELL OUTTA HERE!": "快滚开！",
    "RUN!": "跑！",
    "GO GO GO!": "走！走！走！",
    "Grenade! Get back!": "手雷！退后！",
    "Hold on, I've got a grenade!": "等等，我有手雷！",
    "HEAR A GRENADE!": "手雷！",
    "DAMN!": "该死！",
    "Direct hit!": "正中目标！",
    "ABOUT TIME!": "总算来了！",
    "Thank God!": "谢天谢地！",
    "Target destroyed!": "目标摧毁！",
    "MAN DOWN!": "有人倒了！",
    "MELEK!": "卫生员！",
    "WHERE THE HELL'S THE MEDIC?!": "卫生员死哪去了？！",
    "HE'S DEAD!": "他死了！",
    "WHERE'D THAT SHOT COME FROM?!": "那一枪哪来的？！",
    "STAY DOWN!": "趴着别动！",
    "FORWARD!": "前进！",
    "Straight ahead!": "正前方！",
    "KEEP MOVING UP!": "继续前进！",
    "Dead ahead, move!": "正前方，走！",
    "Come on, start firing!": "快开火！",
    "LAY SOME FIRE DOWN!": "打点火力！",
    "PUT DOWN A BASE OF FIRE!": "架起火力！",
    "NOOOOOO!": "不——！",
    "WE NEED MORE FIRE!": "火力不够！",
    "SHOOT THOSE BASTARDS!": "打死这帮狗杂种！",
    "TAKE IT FIRE!": "遭到射击！",
    "WHERE'S THAT COMING FROM?!": "哪打来的？！",
    "WHERE ARE THEY?!": "他们在哪？！",
    "RETURN FIRE!": "还击！",
    "WE NEED TO FALL BACK!": "得撤了！",
    "TAKING HEAVY FIRE!": "火力太猛了！",
    "THEY'RE NOT LETTING UP!": "他们没停过！",
    "WHERE'S THE RETURN FIRE?!": "还击呢？！",
    "Bring up that ammo!": "弹药拿上来！",
    "WATCH OUR FLANK!": "注意侧翼！",
    "GET MORE FIRE UP HERE!": "上面火力跟上！",
    # ---- Japanese barks (slot-paired with the US set) ----------------------
    "いくぞ!": "走了！",
    "モダモダすんな!": "别磨蹭！",
    "斬新!": "前进！",
    "前へ進め!": "往前推进！",
    "こっちだよねー": "这边走！",
    "さあ一体どうや!": "上！走！走！走！",
    "うたぁぁぁぁ!!": "开火——！",
    "やっちまえ!": "给我狠狠打！",
    "あそこだ!": "在那儿！",
    "よくねー!": "打那儿！",
    "生きて返すな!": "一个都别放回去！",
    "半飛ばせ!": "轰掉他们！",
    "くっそー!敵さんだらけだぞ!": "妈的！到处都是敌人！",
    "奴らどっから撃ってきたんだ!": "这帮人从哪开的枪！",
    "このままでは全滅だいね!": "再这样下去要全军覆没了！",
    "なんとかしてくれー!": "想点办法啊！",
    "狙われてます": "我们被瞄上了。",
    "包囲されてます": "我们被包围了。",
    "てるーだんだー!": "手榴弹！",
    "投擲だー!伏せろー!": "手雷！趴下！",
    "退避": "撤！",
    "くそー! 天竜弾だ!": "妈的！手榴弹！",
    "照らす気目!": "手榴弹！",
    "危ないぞー!": "危险！",
    "これでもくれー!": "吃这个！",
    "手榴弾、投擲!": "手榴弹，投掷！",
    "手榴弾投擲! 逆れ!": "手榴弹投掷！退后！",
    "安全性を伸ばした!自信を!": "销拔了！小心！",
    "敵団転か!気付けろ!": "手榴弹！小心！",
    "ミタロウ!": "看好了！",
    "どうだ": "怎么样！",
    "うおおおおおおおおお!!!": "哦哦哦哦——！",
    "ざまぁみろぼけぇ!": "活该，蠢货！",
    "どんな問題ねー!": "厉害吧！",
    "やったー": "干掉了！",
    "当たったぞー!": "打中了！",
    "いせー!": "卫生员！",
    "エセヘオタヌマ!": "卫生员！这边！",
    "うわあああああしまった": "哇啊，糟了！",
    "先生!先生を呼んでくれ!": "军医！快叫军医！",
    "やられたー!": "被撂倒了！",
    "しっかりしろ!": "挺住！",
    "さあ": "快躲！",
    "格納!!": "隐蔽！",
    "危ねえぞ!": "危险！",
    "そこから離れろ!": "从那儿离开！",
    "逃げと!": "快躲！",
    "頭下げろ!": "低头！",
    # JA_1
    "アムネ!": "手雷！",
    "早っ! タコつぶに!": "快！进掩体！",
    "デリューダンだ!": "是手榴弹！",
    "うっせー!": "烦死了！",
    "死にしろ!": "去死吧！",
    "敵の手榴弾です!": "是敌人的手榴弹！",
    "手油弾投げるぞ!": "扔手榴弹了！",
    "気付けろ!": "小心！",
    "下がれ!": "退后！",
    "僕ら!": "吃这个！",
    "ほらよ!": "接着！",
    "見てろよ!": "看好了！",
    "あなたー!": "打中了！",
    "よーし!": "好！",
    "命中だ!": "命中！",
    "お見事!": "漂亮！",
    "ちょうど!ちょうど!": "正中！正中！",
    "ざまぁみろ!": "活该！",
    "伊勢平和どうだー!": "卫生员！",
    "負傷者だ!": "有人负伤！",
    "手当を!": "快包扎！",
    "一人やられたぞー!": "倒了一个！",
    "血が飛んだーーーーー": "见血了——！",
    "アガーーーーーー!": "啊——！",
    "危ない!": "危险！",
    "スロー!": "趴下！",
    "頭を下げろ!": "低头！",
    "ゴーディアンいれー!": "快进掩体！",
    "逃げろー!": "快跑！",
    "sabes": "别待在空地！",
    "前進!": "前进！",
    "奥へを取るな!": "往前压！",
    "するぞ!": "走了！",
    "早っ!": "快！",
    "アシュー!ヒッパンだー!": "冲啊！",
    "さあ、いったいった!": "走，走了走了！",
    "うだーーーーー!!": "开火——！",
    "今だ!撃てー!": "就是现在！开火！",
    "茨城ケンジーゴーニアリだ!": "开火！",
    "叩きのめせー!": "狠狠揍！",
    "右に回れ!強撃する!": "绕到右边！强攻！",
    "八乃隼すんべぇ!": "集中火力！",
    "撃沈": "遭到猛烈射击！",
    "妙覚醒!": "他们不停火！",
    "どこだー!": "在哪呢！",
    "奴らどっから来たんだー!": "这帮家伙从哪来的！",
    "オケラ勝てると思うなよ!": "别以为赢定了！",
    "くそ!稲子の体現みてぇだ!": "妈的！简直像蝗虫一样多！",
    # JA_2
    "よげろー!": "躲开！",
    "捨てろ!危なーい!": "扔掉！危险！",
    "ちくしょう!デリューランダー!": "混蛋！是手榴弹！",
    "気をつけろ! りゅうだんだー!": "小心！手榴弹！",
    "逃げろー!": "快跑！",
    "くそ!大変!": "妈的！糟糕！",
    "テリューダン行くぞー!": "手榴弹扔了！",
    "くらえ!吹っ飛ばしてやろうぞ!": "吃吧！炸飞你！",
    "逆れー!手榴弾投擲するー!": "退后！要扔手榴弹了！",
    "下がれ!諸君!投げるぞー!": "退后！各位！我扔了！",
    "気をつけろー!": "小心！",
    "足元に注意しろ!": "注意脚下！",
    "よーし、やったー!": "好，干掉了！",
    "片付いた!": "收拾干净了！",
    "おーたれーっ!!": "打中——！",
    "敵中だー!": "打中敌人了！",
    "ど真ん中だいねー!": "正中靶心！",
    "お見事ー!": "漂亮！",
    "イジェオリオメット!": "卫生员！",
    "前線に衛星兵を押せ!": "派卫生兵上前线！",
    "医者に呼び遣いをこせー!": "叫医生来！",
    "ウジョウジャイソー!": "来个人帮忙！",
    "手を貸せ!運ぶぞ!": "搭把手！抬走！",
    "先生を呼べ!": "叫军医来！",
    "失せろー!": "滚开！",
    "頭を下げろー!": "低头！",
    "カグネロー!予言だー!": "快躲！",
    "いかん!逃げろー!": "不好！快跑！",
    "そ": "快躲开！",
    "続いて前進": "继续前进。",
    "全員前へ進め!": "全体前进！",
    "諸君、行くぞー!": "各位，走了！",
    "急速を": "急行军！",
    "みんな前進するぞー!": "大家前进！",
    "全身出動": "全军出动！",
    "醜い鬼め!撃て!": "丑鬼！开火！",
    "行け!一掃攻撃だー!": "上！一举扫清！",
    "うでぇーーーーの": "打——！",
    "逃がすなー!": "别让他们跑了！",
    "狙っていけー!": "瞄准打！",
    "アズコを狙っていけー!": "瞄准那边打！",
    "集中砲火を浴びる": "挨集中炮火了！",
    "キャッツラー攻撃を緩めねえなあ!": "这帮家伙攻击没停过啊！",
    "反撃しよう!反撃!": "还击！还击！",
    "総員反撃せよー!": "全体还击！",
    "くそー!左に注意しろー!": "妈的！注意左边！",
    "攻撃を続けろー!": "继续攻击！",
    # JA_3
    "敵の出龍だー!": "敌人手榴弹！",
    "いけねー!": "糟了！",
    "緊急退避": "紧急撤退！",
    "手榴弾であります!": "是手榴弹！",
    "大変!": "糟了！",
    "離れろ!": "快走！",
    "手榴弾攻撃に入る!": "开始投手榴弹！",
    "下がってろ!テリューなんだ!": "退后！是手榴弹！",
    "待て! 手に入らんがっから!": "等等！我有手榴弹！",
    "爆発するぞー!": "要炸了！",
    "手榴弾でもくらえ!": "吃颗手榴弹！",
    "どうだー!": "怎么样！",
    "一目さぁ!": "一枪一个！",
    "一撃必殺!見たかー!": "一击必杀！看见没！",
    "手こずらせよって": "还真难缠。",
    "人中報告!": "命中报告！",
    "敵を撃破!": "击破敌军！",
    "くそ!あいつがやられた!": "妈的！那家伙中弹了！",
    "負傷者であります": "有人负伤！",
    "SAA!": "啊——！",
    "衛星兵はおらんのかー!": "卫生兵都死哪去了！",
    "くたばりよった!": "死透了！",
    "どこから撃たれた!?": "从哪挨的枪？！",
    "この目": "隐蔽！",
    "遮蔽物を探せ!": "找掩体！",
    "クソッ!離れろ!": "妈的！散开！",
    "ゴーに飛び込め!": "跳进壕沟！",
    "動くな!": "别动！",
    "進めー!": "前进！",
    "いくぞー!": "走了！",
    "前進するぞ!": "前进！",
    "こっちだー!": "这边！",
    "前進を続けろ!": "继续前进！",
    "この先だ!進め!": "就在前面！前进！",
    "早く歌んかー!": "快点开枪啊！",
    "重砲火を浴びせろ!": "给我猛打！",
    "ここを足場に攻撃速攻せよ!": "以这里为据点，速攻！",
    "うでー!": "开火——！",
    "火力が足らんぞ!": "火力不够！",
    "ちくしょうどもを生きて返すなぁ!": "这帮混蛋，一个都别放回去！",
    "的中であります!": "命中！",
    "どこから撃たれた?報告せよ!": "从哪被打的？报告！",
    "敵兵はどこかー!": "敌兵在哪！",
    "直ちに反撃せよ!": "立刻还击！",
    "一時撤退しましょう!": "暂时撤退！",
    "敵応手といえど広めな!": "敌人太多了！",
    # ---- story lines (L1_*) -------------------------------------------------
    "Miller!": "米勒！",
    "Okay, let's see what we've got. Sound off. Turner.": "好，看看我们都有谁。报名字。特纳。",
    "Great, another AJ squared away.": "好，又收拾利索一个。",
    "We thought we were going to win the war all by ourselves.": "我们本以为靠自己能打赢这场仗。",
    "We were wrong.": "我们错了。",
    "Now the other window, Miller!": "换那个窗户，米勒！",
    "Good night.": "晚安咯！",
    "Outstanding, Miller!": "太出色了，米勒！",
    "Damn! Would you look at that? Bet they've been sneaking off the island for days.":
        "妈的，你瞧瞧！这帮家伙肯定偷跑了好几天了。",
    "Thousands of them, I reckon.": "我看得有好几千人。",
    "Good riddance if you ask me.": "要我说，滚了正好。",
    "Put your church key away, Polonsky. See every one of them escaping? Well, guess what? "
    "We'll be seeing them on the next island.":
        "把你那玩意儿收起来，波隆斯基。看见他们一个个跑了吧？猜怎么着？下个岛还得见。",
    "Well, I bet we whoop him for a second time.": "哼，我赌我们能再揍他一顿。",
    "Tokyo Express out of action.": "东京快车已瘫痪。",
    "Come on, Marines! Let's get up there and give them hell!": "上啊，弟兄们！冲上去狠狠揍他们！",
    "Stick a charge in that AA, Miller.": "米勒，给那门高射炮装上炸药。",
    "And now another!": "再来一个！",
    "Okay, on three, I want you to move through these stables and take out the targets.":
        "好，数到三，你穿过这些马厩，把靶子打掉。",
    "One, two, three, go, go, go!": "一、二、三，冲！冲！冲！",
    "Get a move on, Miller! Under the net and through the obstacles! Go! Go!":
        "快点，米勒！钻过网，越过障碍！快！快！",
    "Miller, take out the mortar crew!": "米勒，干掉那个迫击炮组！",
    "Someone get Miller out of that mud!": "谁去把米勒从泥里拉出来！",
    "We've got no cover! Use the smoke grenades!": "没掩体！用烟幕弹！",
    "Get in there, move it!": "进去，快点！",
    "Where is your weapon, Marine?": "你的枪呢，陆战队员？",
    "Aye aye sir!": "是，长官！",
    "Stow it, here he comes!": "别说了，他来了！",
    "Remember, anyone can point and shoot, but if you want to zero your rifle like a warrior, "
    "you'll want to look straight down the sight and snap in.":
        "记住，谁都会瞄着开枪。可想把枪校准得像个老兵，就得顺着准星看过去，稳稳扣下去。",
    "Sergeant, they're dug in just too damn tight there!": "中士，他们在那儿挖得太死了！",
    "Damn right! Now let's finish this!": "没错！把它干完！",
    "Miller, get on that machine gun and give us some covering fire!":
        "米勒，去架机关枪，给我们掩护！",
    "Miller, I'm talking to you. Over here, son.": "米勒，我在跟你说话。过来，孩子。",
    "Hey Mac, what's the scuttlebutt on the new honcho?": "嘿，麦克，新来的头儿有什么说法？",
    "I hear the bastard's tough as nails.": "听说那家伙是个狠角色。",
    "You're the new recruit, Sergeant Roebuck.": "你就是新来的兵，罗巴克中士。",
    "Ten hot!": "立正！",
    "Polanski!": "波隆斯基！",
    "Aye, sir!": "是，长官！",
    "Get over to that table and pick up a rifle, Miller. Double time!":
        "去那张桌子拿支步枪，米勒。跑步！",
    "The rest of you, move out to the rifle range for some dry fire.": "其余的人去靶场练空枪。",
    "Smoke grenades next. You'll use them to conceal your movements on the battlefield and "
    "confuse the enemy. Take a few and throw one through the top floor window of that barn.":
        "接下来是烟幕弹。用它遮住你的行动，让敌人摸不清。拿几个，往那间谷仓的顶层窗户扔一个。",
    "Don't think I'm letting you off with forgetting your rifle, Miller. One lap around the hill. "
    "I'll be waiting at the end.": "米勒，忘带枪这事我可不会就这么算了。绕山跑一圈，我在终点等你。",
    "Okay, we've got smoke! Go, go, go!": "好，烟起来了！冲！冲！冲！",
    "Hey, Sergeant, I got a tunnel down here.": "中士，我这下面有个地道。",
    "Anderson, burn it out. Everyone stay back.": "安德森，把它烧了。都退后。",
    "What are you waiting for, Miller? An engraved invitation? Get going!":
        "还等什么，米勒？等你请帖啊？快去！",
    "Oh, you really are the best of the best, aren't you, Miller? Get in there!":
        "哦，你真是精英中的精英啊，米勒？上啊！",
    "Come on, buddy! We got you covered!": "顶住，兄弟！有我们掩护！",
    "Polonsky, get some smoke up there! Anderson Miller, when the smoke hits, find cover near the top!":
        "波隆斯基，往上面打烟！安德森、米勒，烟一起来就到上面找掩体！",
    "You think we've got all day, Miller? Pick up your Thompson. Chop, chop. Let's go.":
        "米勒，你以为我们有一整天？把你的汤普森拿上。快点快点，走。",
    "Miller! There's a Thompson on the table. Get it now!": "米勒！桌上那把汤普森，马上拿！",
    "Okay, last double A. Get a charge on it, Miller.": "好，最后一门高射炮。米勒，装炸药。",
    "Look at those ships, they're bugging out!": "看那些船，他们要跑了！",
    "Hey, up there!": "嘿，上面！",
    "Damn it, that's one of our birds! He's ditching!": "该死，那是我们的飞机！他要迫降了！",
    "I'll tell you right now, until we take out that artillery, we can just forget about air support.":
        "我直说吧：不把那炮干掉，就别指望空中支援了。",
    "Not too shabby, Miller. We might make you a warrior yet.":
        "还行，米勒。说不定能把你练成个兵。",
    "Okay, let's see how you handle grenades. Go grab some from the ordinance table over there.":
        "好，看看你手榴弹玩得怎么样。去那边桌子拿几个。",
    "Okay, Miller. Shoot the helmets off the scarecrows.": "好，米勒。把稻草人上的钢盔打下来。",
    "Okay, good.": "好，不错。",
    "Okay, that covers grenades. Now follow me to the assault course.":
        "好，手榴弹就到这。跟我去突击训练场。",
    "I want suppressing fire on that hill!": "那座山头上给我火力压制！",
    "Get up, Miller! You're not dead till I say so!": "起来，米勒！我没说死你就没死！",
    "Anderson, I want some flame on that bunker. Get up that hill and get on it!":
        "安德森，那个碉堡给我烧了。爬上山去，动手！",
    "Miller, you go with him.": "米勒，你跟着他。",
    "Keep moving, Marines! Get up there!": "继续走，弟兄们！往上冲！",
    "RRAAAAGH! STORM THE HILL!": "冲啊！拿下山头！",
    "Nice work! Anderson, go and check it out!": "干得好！安德森，过去看看！",
    "TROOPWIRE!": "绊线！",
    "Ugh!": "呃啊！",
    "Anderson! Damn it!": "安德森！该死！",
    "Miller, pick up the flamethrower and...": "米勒，拿上火焰喷射器，然后……",
    "Get in there, Marines! Go! Go! Go!": "上，弟兄们！冲！冲！冲！",
    "Wow! Excellent fruit-killing skills you've got there, Miller. Now stop messing around!":
        "嚯，米勒，你这枪法练得挺溜啊。行了，别磨蹭了！",
    "The targets are over here, soldier.": "靶子在这边，士兵。",
    "Don't get too excited, Marine. Real targets move and fire back at you.":
        "别得意，陆战队员。真靶子会动，还会朝你开枪。",
    "Not bad. Not bad at all.": "不错，相当不错。",
    "Polanski, take care of that room.": "波隆斯基，那间屋交给你。",
    "All clear!": "安全了！",
    "Take covering positions!": "各就各位，准备掩护！",
    "Miller, get out of the way of the fire!": "米勒，躲开火！",
    "Oh yeah! Now they'll get theirs! But good!": "太棒了！这下他们完蛋了！",
    "Let's go, men! Move! Move! Move!": "走，弟兄们！动起来！动起来！",
    "Miller! Get over here and shoot these targets!": "米勒！过来打这些靶子！",
    "Miller, keep this up and I will lock you on but good. Do you read me?":
        "米勒，你再这样，我就把你关禁闭关到长记性。听明白了吗？",
    "Miller! Get over here, that's an order!": "米勒！给我过来，这是命令！",
    "Miller, the narrow end with the hole is where the bullet comes out. Now get shooting!":
        "米勒，带孔的那头才是子弹出来的地方。赶紧开枪！",
    "I think they've got us pinned down here, Sergeant!": "中士，我们被压制住了！",
    "Keep your heads down.": "都低头。",
    "Command says 161st has Shermans inbound to our location.":
        "指挥部说第161团的谢尔曼坦克正往我们这边来。",
    "Looks like the cavalry's arrived, boys!": "咱们的救兵到了，弟兄们！",
    "We got armor! Yah!": "我们的坦克到了！好啊！",
    "They're dug in deep and we gotta get through them to take out that artillery.":
        "他们挖得很深，得从他们身上碾过去才能干掉那门炮。",
    "This must be Tenaro Village. We need to cut through this mess and take out those AA guns.":
        "这应该就是特纳罗村。得穿过这片乱摊子，把那些高射炮拔掉。",
    "The Japanese leveled the village. Those sneaky bastards are using the ruins as cover.":
        "日本人把村子夷平了。这帮鬼东西就拿废墟当掩体。",
    "They don't give up easy, do they? Keep pushing them back, boys.":
        "这帮家伙还真不肯松手。继续把他们压回去，弟兄们。",
    "See that window on the ground floor? Toss a frag grenade through it!":
        "看见一楼那个窗户没？往里扔颗手雷！",
    "You're up first, Miller. Pick up a Thompson from the table.": "你先上，米勒。去桌上拿把汤普森。",
    "All right, Marines, move to the close quarters range. Follow me.":
        "好，弟兄们，去近战靶场。跟我走。",
    "Okay, time to recap. Some basic combat maneuvers. Just like in TBS. Miller, you will demonstrate.":
        "好，复习一下基本战术动作。跟训练营里一样。米勒，你来做示范。",
    "Don't worry, Miller. I'll be there every step of the way.": "别担心，米勒。我会一路带着你。",
    "Get some fire in there!": "往里面打！",
    "Roast you sons of bitches!": "把你们这帮狗娘养的烤了！",
    "Knock it off, Polonsky. Miller, get over there and clear it out. The rest of you stack up and "
    "wait for my signal.": "别闹了，波隆斯基。米勒，你过去清干净。其他人贴墙待命，等我信号。",
    "Stop flailing around, will ya? Hey, Fletch, I think this one's drowning. Grab him!":
        "别乱扑腾了行不行？嘿，弗莱奇，我看这家伙要淹死了。抓住他！",
    "Ugh! The bastard's over there!": "咳！那狗东西在那边！",
    "Outstanding": "干得漂亮！",
    "This can't be happening!": "这不可能！",
}


def norm(text):
    return re.sub(r'\s+', ' ', text).strip().upper()


def build():
    table = {}
    for key, value in T.items():
        k = norm(key)
        if k in table and table[k] != value:
            raise SystemExit('conflicting translation for %r' % k)
        table[k] = value
    return table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(DEF_JSON))
    ap.add_argument('--report', default=str(DEF_REPORT))
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    path = Path(args.json)
    table = build()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    before = {name: rec['asr_text'] for name, rec in data.items()}

    missing, filled = [], 0
    for name, rec in data.items():
        cn = table.get(norm(rec['asr_text']))
        if cn is None:
            missing.append((name, rec['asr_text']))
            continue
        rec['translation'] = cn
        rec['note'] = NOTE
        filled += 1

    if missing:
        print('UNTRANSLATED:')
        for name, text in missing:
            print('  %s %r' % (name, text))
        raise SystemExit('%d entries without a translation' % len(missing))

    lines = ['file\tasr_text\ttranslation']
    for name, rec in data.items():
        lines.append('%s\t%s\t%s' % (name, rec['asr_text'].replace('\t', ' '),
                                     rec['translation'].replace('\t', ' ')))
    report = Path(args.report)
    if not args.dry:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes('\n'.join(lines).encode('utf-8') + b'\n')

    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if args.dry:
        print('dry run: %d entries, %d unique texts' % (len(data), len(table)))
        return
    path.write_bytes(text.encode('utf-8'))

    check = json.loads(path.read_text(encoding='utf-8'))
    assert list(check) == list(data), 'key order changed'
    assert {n: r['asr_text'] for n, r in check.items()} == before, 'asr_text changed'
    assert all(r['translation'] for r in check.values()), 'empty translation left'
    assert not path.read_bytes().startswith(b'\xef\xbb\xbf'), 'BOM added'
    assert b'\r' not in path.read_bytes(), 'CR found'
    print(json.dumps({'filled': filled, 'unique': len(table),
                      'report': str(report)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
