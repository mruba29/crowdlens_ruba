import sys, os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import store
from analysis import AnalysisState


def test_incidents_crud(tmp_path):
    store.init()
    # Test incident creation and updates
    inc = store.create_incident(
        zone="Gate 3 North",
        severity="RED",
        title="Severe crowd accumulation at turnstiles",
        description="Density exceeded 4.5 ppm2 with reverse flow",
        recommended_action="Halt ticket ingress and open side bypass gates",
        video_id="test_vid_123"
    )
    assert inc is not None
    assert isinstance(inc, dict)
    assert inc["zone"] == "Gate 3 North"
    assert inc["severity"] == "RED"
    assert inc["status"] == "OPEN"
    assert inc["video_id"] == "test_vid_123"
    inc_id = inc["id"]

    # Update status to DISPATCHED
    updated = store.update_incident(
        inc_id,
        status="DISPATCHED",
        operator_notes="Team Alpha en route to Gate 3"
    )
    assert updated is not None
    assert updated["status"] == "DISPATCHED"
    assert updated["operator_notes"] == "Team Alpha en route to Gate 3"

    # List incidents
    incidents = store.list_incidents()
    assert len(incidents) >= 1
    found = [i for i in incidents if i["id"] == inc_id]
    assert len(found) == 1


def test_video_metrics_summary_persistence():
    store.init()
    # Insert or update a test video record
    videos = store.list_videos()
    if videos:
        vid = videos[0]["id"]
        sample_summary = {
            "peak_people": 85,
            "peak_density": 3.4,
            "max_score": 72.5,
            "final_level": "ORANGE",
            "people_timeline": [
                {"t_offset_sec": 0.0, "people_count": 10, "density_ppm2": 0.5, "score": 20.0, "level": "GREEN"},
                {"t_offset_sec": 5.0, "people_count": 85, "density_ppm2": 3.4, "score": 72.5, "level": "ORANGE"},
            ],
            "zone_distribution": [{"name": "Zone A", "count": 85, "pct": 100}]
        }
        store.update_video_metrics(
            vid,
            status="completed",
            people=85,
            density=3.4,
            score=72.5,
            level="ORANGE",
            metrics_summary=sample_summary
        )

        v = store.get_video(vid)
        assert v is not None
        assert v["last_people"] == 85
        assert v["last_score"] == 72.5
        assert v["last_level"] == "ORANGE"
        assert v["metrics_summary"] is not None
        assert v["metrics_summary"]["peak_people"] == 85
        assert len(v["metrics_summary"]["people_timeline"]) == 2


def test_analysis_state_queue_and_pause():
    state = AnalysisState()
    assert state.is_paused is False
    assert state.queue == []

    # Queue videos
    state.queue_add(["vid_a", "vid_b", "vid_c"])
    assert [q["video_id"] for q in state.queue] == ["vid_a", "vid_b", "vid_c"]

    # Cancel one from queue
    cancelled = state.cancel_queued("vid_b")
    assert cancelled is True
    assert [q["video_id"] for q in state.queue] == ["vid_a", "vid_c"]

    # Pause and resume events
    state.pause()
    assert state.is_paused is True
    assert state._pause.is_set()

    state.resume()
    assert state.is_paused is False
    assert not state._pause.is_set()


def test_sample_videos_catalogue():
    import main
    samples = main.SAMPLE_VIDEOS
    assert len(samples) >= 7
    categories = {s["category"] for s in samples}
    expected = {
        "Temple / Festival",
        "Stadium / Sports",
        "Concert / Music Festival",
        "Public Gathering",
        "Transport Hub / Railway / Metro",
        "Procession",
        "Protest / Rally",
    }
    for exp in expected:
        assert exp in categories, f"Missing category in sample catalogue: {exp}"

    # Verify each sample has required fields and licensing
    for s in samples:
        assert s["id"]
        assert s["title"]
        assert s["source_name"]
        assert s["source_url"].startswith("http")
        assert s["license"]
        assert isinstance(s["is_synthetic"], bool)
        assert s["scenario_type"]
        assert s["description"]


def test_category_normalization():
    import main
    assert main._norm_category("temple") == "Temple / Festival"
    assert main._norm_category("Stadium") == "Stadium / Sports"
    assert main._norm_category("Concert") == "Concert / Music Festival"
    assert main._norm_category("Metro Hub") == "Transport Hub / Railway / Metro"
    assert main._norm_category("Parade / Procession") == "Procession"
    assert main._norm_category("Rally") == "Protest / Rally"
    assert main._norm_category("Public Gathering") == "Public Gathering"
    assert main._norm_category(None) == "Other"


