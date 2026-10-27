# -*- coding: utf-8 -*-
"""临时验证：象棋/掼蛋联机进对局 + 身份计算失败时的降级（禁止红屏）。跑完就删。"""
import asyncio
import traceback

import app
from core.net import session as S
from core.net.session import RoomSession
from core.router import Router
from core.views import room_view
from games.chess import views as chess_views
from games.guandan.views import play_view as gd_play

app._register_core_routes()


class FakePage:
    def __init__(self):
        self.controls = []
        self.tasks = []

    def add(self, *controls):
        self.controls.extend(controls)

    def run_task(self, handler, *args, **kwargs):
        import inspect
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("handler must be a coroutine function")
        task = asyncio.ensure_future(handler(*args, **kwargs))
        self.tasks.append(task)
        return task

    def update(self):
        pass


async def _errors(pages, ticks=40):
    errs = []
    for _ in range(ticks):
        await asyncio.sleep(0.1)
        for page in pages:
            for t in page.tasks:
                if t.done() and t.exception() is not None:
                    errs.append(t.exception())
                    traceback.print_exception(type(t.exception()),
                                              t.exception(),
                                              t.exception().__traceback__)
    return errs


async def case_two_sides(game_id, title, route, code):
    host_s = RoomSession.create(f"{title}测试", game_id, title, code,
                                "房主", seats=4 if game_id == "guandan" else 2)
    S._CURRENT = host_s
    host_s.drain()
    guest_s = RoomSession.join(host_s.info, code.lower(), "客人")
    assert guest_s is not None and guest_s.wait_join(5.0), guest_s.join_error
    await asyncio.sleep(1.0)

    hp, gp = FakePage(), FakePage()
    hr, gr = Router(hp), Router(gp)
    hr.navigate("/room")
    S._CURRENT = guest_s
    gr.navigate("/multiplayer")
    gr.invalidate("/room")
    gr.navigate("/room")
    await asyncio.sleep(0.8)

    S._CURRENT = host_s
    host_s.begin_game()
    room_view._enter_game_route(hr.navigate, route)
    S._CURRENT = guest_s
    errs = await _errors([hp, gp])

    ok = hr.current_path() == route and gr.current_path() == route and not errs
    extra = ""
    if game_id == "guandan":
        play = gd_play._CURRENT_PLAY
        synced = bool(play is not None and play._synced)
        extra = f"客人同步发牌={synced}"
        ok = ok and synced
    else:
        role = chess_views._ACTIVE.role if chess_views._ACTIVE else None
        extra = f"本机身份={role}"
        ok = ok and role in ("w", "b", "spectator")
    print(f"  [{title}] 房主={hr.current_path()} 客人={gr.current_path()} "
          f"异常={len(errs)} {extra} -> {'OK' if ok else 'FAIL'}")
    S._CURRENT = None
    host_s.close()
    guest_s.close()
    await asyncio.sleep(0.3)
    return ok


async def case_roster_boom():
    """核心回归：roster() 抛异常时，对局页必须照常打开（不冒到事件处理里）。"""
    host_s = RoomSession.create("降级测试", "chess", "国际象棋", "DGR01",
                                "房主", seats=2)
    S._CURRENT = host_s
    host_s.drain()
    page = FakePage()
    router = Router(page)
    router.navigate("/room")

    orig = RoomSession.roster

    def boom(self):
        raise RuntimeError("模拟席位表炸掉")

    RoomSession.roster = boom
    try:
        room_view._enter_game_route(router.navigate, "/g/chess/play")
        errs = await _errors([page])      # 席位表持续坏着，轮询也要扛住
    except Exception as exc:                       # 不该冒出来
        print(f"  [降级] 异常冒到了事件处理：{exc!r} -> FAIL")
        RoomSession.roster = orig
        host_s.close()
        return False
    finally:
        RoomSession.roster = orig

    role = chess_views._ACTIVE.role if chess_views._ACTIVE else None
    ok = router.current_path() == "/g/chess/play" and not errs
    print(f"  [降级] 对局页仍打开={router.current_path()} 身份={role} "
          f"异常={len(errs)} -> {'OK' if ok else 'FAIL'}")
    S._CURRENT = None
    host_s.close()
    await asyncio.sleep(0.3)
    return ok


async def main():
    a = await case_two_sides("guandan", "掼蛋", "/g/guandan/play", "VER01")
    b = await case_two_sides("chess", "国际象棋", "/g/chess/play", "VER02")
    c = await case_roster_boom()
    return a and b and c


if __name__ == "__main__":
    print("\n结果:", "PASS" if asyncio.run(main()) else "FAIL")
