import { Ball } from "../../model/ball"
import { Outcome } from "../../model/outcome"
import { Controller } from "../controller"
import { Session } from "../../network/client/session"
import { Aim } from "../aim"
import { EightBall } from "./eightball"

const flipType = (t: number): number => (t === 1 ? 2 : t === 2 ? 1 : 0)

/**
 * ATR Game 0.5 — 中式八球（本地双人 / hotseat）。
 *
 * 上游的 EightBall 用 Session.p1type 表示「网络座位上的我」的球组，
 * 本地单设备模式没有 P2，所以两人轮流用一台设备时会一直按同一个球组判定。
 *
 * 这里维护两组球和当前击球者，在每次 update 前把当前击球者的球组写进
 * Session.p1type，让上游的犯规 / 瞄准 / 胜负逻辑照常工作；回合结束后按
 * 中式八球规则换人，再写回下一人的球组。保持 isSinglePlayer=true，
 * 不返回 WatchAim（本地没有对端能把控制权交回来）。
 *
 * 与上游美式八球的另一处差异：未清台先打进 8 号球直接判负。
 */
export class Chinese8Ball extends EightBall {
  private active: 0 | 1 = 0
  private groups: [number, number] = [0, 0]
  private scores: [number, number] = [0, 0]

  constructor(container: any) {
    super(container)
    // 让 assets/billiards3d/atr_chinese8.js 的旧补丁跳过，避免重复包装。
    ;(this as any).__atrChinese8 = true
    this.publish()
  }

  rulename = "eightball" // 复用上游八球球桌模型 / 资源

  private publish(): void {
    ;(globalThis as any).__atrHotseat = {
      active: this.active + 1,
      groups: [this.groups[0], this.groups[1]],
      scores: [this.scores[0], this.scores[1]],
    }
  }

  private syncSession(): void {
    Session.getInstance().p1type = this.groups[this.active] || 0
  }

  private addScore(outcome: Outcome[]): void {
    const count = Outcome.potCount(outcome)
    if (count <= 0) return
    this.scores[this.active] += count
    // super.update() 会先用 addMyScore 记给「本机玩家」；这里按 hotseat 的
    // 两位玩家重新分配（TS private 字段在运行时就是普通属性）。
    const session = Session.getInstance()
    const store = (session as any).scoreByClientId as Record<string, number>
    if (store) {
      store[session.clientId] = this.scores[0]
      store[session.opponentClientId ?? "opponent"] = this.scores[1]
    }
  }

  nextCandidateBall(type?: number): Ball | undefined {
    this.syncSession()
    return super.nextCandidateBall(type)
  }

  update(outcome: Outcome[]): Controller {
    const session = Session.getInstance()
    const pots = Outcome.pots(outcome)
    const eightPotted = pots.some((b) => b.label === 8)
    const won = super.isEndOfGame(outcome)

    // 中式八球：未清台先打进 8 号球判负，而不是像美式八球那样摆回。
    if (eightPotted && !won) {
      return this.handleGameEnd(false, "8-ball pocketed before clearing group")
    }

    const foul = super.foulReason(outcome) !== null
    // 关键：先让上游按「当前击球者」的球组检查犯规、定组、瞄准。
    this.syncSession()
    const controller = super.update(outcome)

    // 开放球台：按本杆合法进的球给两位玩家定组（不依赖上游 Session.p1type，
    // 本地 hotseat 的上游逻辑并不会把分组回灌给“本机玩家”）。
    if (this.groups[this.active] === 0 && !foul) {
      const solids = pots.filter((b) => (b.label || 0) >= 1 && (b.label || 0) <= 7)
      const stripes = pots.filter((b) => (b.label || 0) >= 9 && (b.label || 0) <= 15)
      if (solids.length > 0 && stripes.length === 0) {
        this.groups[this.active] = 1
        this.groups[this.active === 0 ? 1 : 0] = 2
      } else if (stripes.length > 0 && solids.length === 0) {
        this.groups[this.active] = 2
        this.groups[this.active === 0 ? 1 : 0] = 1
      }
    }
    this.syncSession()
    this.addScore(outcome)

    const myGroup = this.groups[this.active]
    const ownPot = pots.some((b) => {
      const label = b.label || 0
      if (myGroup === 1) return label >= 1 && label <= 7
      if (myGroup === 2) return label >= 9 && label <= 15
      return label !== 8
    })

    const switchTurn = won ? false : foul || !ownPot
    if (switchTurn) {
      this.active = this.active === 0 ? 1 : 0
      this.syncSession()
    }
    this.publish()

    // 换人且不是犯规（犯规沿用 super 的 PlaceBall / 自由球流程）：
    // 重建 Aim，让它按新击球者的球组重新选目标球。
    if (switchTurn && !foul && !won) {
      return new Aim(this.container)
    }
    return controller
  }
}
