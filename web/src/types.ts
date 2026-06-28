export type Role = 'zhu' | 'zhong' | 'fan' | 'nei' | 'unknown';
export type Phase = 'judge' | 'draw' | 'play' | 'discard' | 'response' | 'game_over';
export type CardName =
  | 'sha'
  | 'shan'
  | 'tao'
  | 'wuzhongshengyou'
  | 'guohechaiqiao'
  | 'shunshouqianyang'
  | 'jiedaosharen'
  | 'nanmanruqin'
  | 'wanjianqifa'
  | 'taoyuanjieyi'
  | 'wugufengdeng'
  | 'juedou'
  | 'wuxiekeji'
  | 'lebusishu'
  | 'shandian'
  | 'zhugeliannu'
  | 'qinggangjian'
  | 'cixiongshuanggujian'
  | 'hanbingjian'
  | 'qinglongyanyuedao'
  | 'zhangbashemao'
  | 'guanshifu'
  | 'fangtianhuaji'
  | 'qilingong'
  | 'baguazhen'
  | 'renwangdun'
  | 'jueying'
  | 'dilu'
  | 'zhuahuangfeidian'
  | 'dawan'
  | 'chitu'
  | 'zixing';

export interface AIConfig {
  name: string;
  base_url: string;
  api_key: string;
  model: string;
  temperature?: number;
}

export interface Card {
  id: string;
  name: CardName;
  suit: string;
  rank: string;
}

export interface Action {
  action_id: string;
  type: string;
  card_id?: string | null;
  card_name?: CardName | null;
  target_player_id?: string | null;
  secondary_target_player_id?: string | null;
  target_card_ids?: string[] | null;
  target_card_names?: CardName[] | null;
  label: string;
}

export interface PendingResponse {
  type: 'respond_shan' | 'respond_sha' | 'dying_tao' | 'discard' | 'wuxie';
  player_id: string;
  source_player_id?: string | null;
  origin_player_id?: string | null;
  target_player_id?: string | null;
  secondary_target_player_id?: string | null;
  card_id?: string | null;
  card_name?: CardName | null;
  effect_type?: string | null;
  target_player_ids?: string[] | null;
  remaining_player_ids?: string[] | null;
  queue_player_ids?: string[] | null;
  responded_player_ids?: string[] | null;
  required_count?: number | null;
}

export interface Equipment {
  weapon?: Card | null;
  armor?: Card | null;
  attack_horse?: Card | null;
  defense_horse?: Card | null;
}

export interface Player {
  id: string;
  name: string;
  is_human: boolean;
  role: Role;
  role_public: boolean;
  hp: number;
  max_hp: number;
  alive: boolean;
  hand: Card[];
  hand_count: number;
  used_sha_this_turn: boolean;
  equipment: Equipment;
  judgment_area: Card[];
}

export interface DistanceInfo {
  source_player_id: string;
  target_player_id: string;
  distance: number;
  attack_range: number;
  in_attack_range: boolean;
}

export interface GameState {
  game_id: string;
  players: Player[];
  deck_count: number;
  discard_count: number;
  current_player_index: number;
  phase: Phase;
  pending_response?: PendingResponse | null;
  round: number;
  recent_events: string[];
  winner?: string | null;
  distances: DistanceInfo[];
  legal_actions: Action[];
}

export interface CreateGameResponse {
  game_id: string;
  state: GameState;
}
