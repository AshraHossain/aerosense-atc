"""
WebSocket endpoint + background graph execution.
Each scenario run gets an asyncio.Queue. The graph runs in a daemon thread
and pushes serialised messages into the queue via call_soon_threadsafe.
The WS handler drains the queue until it sees the sentinel (None).
"""

import asyncio
import json
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.graph import atc_app

router = APIRouter()

# scenario_id -> asyncio.Queue[str | None]
_runs: dict[str, asyncio.Queue] = {}


def _run_graph(
    scenario: dict,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    def push(msg: dict) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, json.dumps(msg))
        except Exception:
            pass

    try:
        prev_event_count = len(scenario.get("events", []))
        final_state: dict | None = None

        for state in atc_app.stream(scenario, stream_mode="values"):
            final_state = state
            events: list = state.get("events", [])
            new_events = events[prev_event_count:]
            prev_event_count = len(events)

            push({
                "type": "phase_complete",
                "phase": state.get("current_phase", "unknown"),
                "phases_completed": state.get("phases_completed", []),
                "event": new_events[-1] if new_events else None,
                "stats": {
                    "flights":    len(state.get("flights", [])),
                    "conflicts":  len(state.get("conflicts", [])),
                    "clearances": len(state.get("clearances", [])),
                },
            })

        if final_state:
            health = final_state.get("system_health") or {}
            push({
                "type": "scenario_complete",
                "phases_completed": final_state.get("phases_completed", []),
                "final_report":     final_state.get("final_report", ""),
                "system_health":    dict(health),
                "stats": {
                    "flights":        len(final_state.get("flights", [])),
                    "conflicts":      len(final_state.get("conflicts", [])),
                    "clearances":     len(final_state.get("clearances", [])),
                    "do178c_traces":  len(final_state.get("do178c_traces", [])),
                },
            })

    except Exception as exc:
        push({"type": "error", "message": str(exc)})
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)


def start_run(scenario: dict, loop: asyncio.AbstractEventLoop) -> None:
    sid = scenario["scenario_id"]
    queue: asyncio.Queue = asyncio.Queue()
    _runs[sid] = queue
    thread = threading.Thread(
        target=_run_graph,
        args=(scenario, queue, loop),
        daemon=True,
    )
    thread.start()


@router.websocket("/ws/{scenario_id}")
async def ws_endpoint(ws: WebSocket, scenario_id: str) -> None:
    await ws.accept()

    queue = _runs.get(scenario_id)
    if queue is None:
        await ws.send_text(json.dumps({"type": "error", "message": "Scenario not found"}))
        await ws.close()
        return

    try:
        while True:
            raw = await queue.get()
            if raw is None:
                break
            await ws.send_text(raw)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _runs.pop(scenario_id, None)
        try:
            await ws.close()
        except Exception:
            pass
