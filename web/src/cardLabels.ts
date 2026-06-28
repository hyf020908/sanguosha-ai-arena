import { Fragment, createElement } from 'react';
import type { ReactNode } from 'react';
import type { Action, Card, CardName } from './types';

export const cardLabels: Record<CardName, string> = {
  sha: '杀',
  shan: '闪',
  tao: '桃',
  wuzhongshengyou: '无中生有',
  guohechaiqiao: '过河拆桥',
  shunshouqianyang: '顺手牵羊',
  jiedaosharen: '借刀杀人',
  nanmanruqin: '南蛮入侵',
  wanjianqifa: '万箭齐发',
  taoyuanjieyi: '桃园结义',
  wugufengdeng: '五谷丰登',
  juedou: '决斗',
  wuxiekeji: '无懈可击',
  lebusishu: '乐不思蜀',
  shandian: '闪电',
  zhugeliannu: '诸葛连弩',
  qinggangjian: '青釭剑',
  cixiongshuanggujian: '雌雄双股剑',
  hanbingjian: '寒冰剑',
  qinglongyanyuedao: '青龙偃月刀',
  zhangbashemao: '丈八蛇矛',
  guanshifu: '贯石斧',
  fangtianhuaji: '方天画戟',
  qilingong: '麒麟弓',
  baguazhen: '八卦阵',
  renwangdun: '仁王盾',
  jueying: '绝影',
  dilu: '的卢',
  zhuahuangfeidian: '爪黄飞电',
  dawan: '大宛',
  chitu: '赤兔',
  zixing: '紫骍'
};

const suitIcons: Record<string, string> = {
  heart: '♥',
  diamond: '♦',
  club: '♣',
  spade: '♠'
};

const areaLabels: Record<string, string> = {
  hand: '随机手牌',
  equipment: '装备区',
  judgment: '判定区'
};

export function translateCardName(name?: CardName | null) {
  return name ? cardLabels[name] : '';
}

export function suitIcon(suit?: string | null) {
  return suit ? suitIcons[suit] ?? suit : '';
}

export function suitColorClass(suit?: string | null) {
  return suit === 'heart' || suit === 'diamond' ? 'suit-red' : 'suit-black';
}

export function formatCard(card?: Pick<Card, 'name' | 'suit' | 'rank'> | null) {
  if (!card) {
    return '';
  }
  return `${translateCardName(card.name)}（${suitIcon(card.suit)} ${card.rank}）`;
}

function formatActionCard(action: Action) {
  if (!action.card_name) {
    return '';
  }
  return `${translateCardName(action.card_name)}${action.card_suit && action.card_rank ? `（${suitIcon(action.card_suit)} ${action.card_rank}）` : ''}`;
}

function formatSelected(action: Action) {
  if (!action.selected_area) {
    return '';
  }
  if (action.selected_area === 'hand') {
    return '随机手牌';
  }
  const area = areaLabels[action.selected_area] ?? action.selected_area;
  const selected =
    action.selected_card_name && action.selected_card_suit && action.selected_card_rank
      ? `${area}：${translateCardName(action.selected_card_name)}（${suitIcon(action.selected_card_suit)} ${action.selected_card_rank}）`
      : area;
  return selected;
}

export function formatActionLabel(action: Action) {
  if (action.type === 'end_phase') {
    return '结束出牌';
  }
  if (action.type === 'pass_response') {
    return action.label || '不响应';
  }
  if (action.type === 'discard_cards') {
    return action.label;
  }
  const card = formatActionCard(action);
  if (action.type === 'equip_card') {
    return `装备：${card}`;
  }
  if (action.type === 'wugu_choose') {
    return `选择 ${card}`;
  }
  if (action.card_name === 'guohechaiqiao' || action.card_name === 'shunshouqianyang') {
    return `${translateCardName(action.card_name)} → ${action.target_player_name ?? ''} 的${formatSelected(action)}`;
  }
  if (action.card_name === 'jiedaosharen') {
    return `${card} → ${action.target_player_name ?? ''} 杀 ${action.secondary_target_player_name ?? ''}`;
  }
  if (action.target_player_name && !['wuzhongshengyou', 'shandian'].includes(action.card_name ?? '')) {
    return `${card} → ${action.target_player_name}`;
  }
  return card || action.label;
}

export function renderCardInline(
  name?: CardName | null,
  suit?: string | null,
  rank?: string | null
): ReactNode {
  if (!name) {
    return null;
  }
  return createElement(
    Fragment,
    null,
    translateCardName(name),
    suit && rank
      ? createElement(
          Fragment,
          null,
          '（',
          createElement('span', { className: suitColorClass(suit) }, suitIcon(suit)),
          ` ${rank}）`
        )
      : null
  );
}

function renderSelected(action: Action): ReactNode {
  if (!action.selected_area) {
    return null;
  }
  if (action.selected_area === 'hand') {
    return '随机手牌';
  }
  const area = areaLabels[action.selected_area] ?? action.selected_area;
  if (action.selected_card_name && action.selected_card_suit && action.selected_card_rank) {
    return createElement(
      Fragment,
      null,
      `${area}：`,
      renderCardInline(action.selected_card_name, action.selected_card_suit, action.selected_card_rank)
    );
  }
  return area;
}

export function renderActionLabel(action: Action): ReactNode {
  if (action.type === 'end_phase') {
    return '结束出牌';
  }
  if (action.type === 'pass_response' || action.type === 'discard_cards') {
    return action.label || '不响应';
  }
  const card = renderCardInline(action.card_name, action.card_suit, action.card_rank);
  if (action.type === 'equip_card') {
    return createElement(Fragment, null, '装备：', card);
  }
  if (action.type === 'wugu_choose') {
    return createElement(Fragment, null, '选择 ', card);
  }
  if (action.card_name === 'guohechaiqiao' || action.card_name === 'shunshouqianyang') {
    return createElement(
      Fragment,
      null,
      `${translateCardName(action.card_name)} → ${action.target_player_name ?? ''} 的`,
      renderSelected(action)
    );
  }
  if (action.card_name === 'jiedaosharen') {
    return createElement(
      Fragment,
      null,
      card,
      ` → ${action.target_player_name ?? ''} 杀 ${action.secondary_target_player_name ?? ''}`
    );
  }
  if (action.target_player_name && !['wuzhongshengyou', 'shandian'].includes(action.card_name ?? '')) {
    return createElement(Fragment, null, card, ` → ${action.target_player_name}`);
  }
  return card || action.label;
}
