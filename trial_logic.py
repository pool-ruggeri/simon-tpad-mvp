"""Pure Simon trial generation, fixed visual scheduling, and hardware scoring."""

from dataclasses import dataclass, field
import random

from tpad_serial import Event


@dataclass
class Trial:
    number: int
    block: str
    color: str
    side: str
    lower_ms: int | None = None
    upper_ms: int | None = None
    lower_sequence: int | None = None
    upper_sequence: int | None = None
    stimulus_flip_host_s: float | None = None
    offset_flip_host_s: float | None = None
    visual_end_host_s: float | None = None
    finalized_host_ns: int | None = None
    completed: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def correct_response(self):
        return 1 if self.color == "blue" else 2

    @property
    def congruency(self):
        correct_side = "left" if self.correct_response == 1 else "right"
        return "congruent" if self.side == correct_side else "incongruent"


def make_trials(practice_count, experimental_count, seed):
    rng = random.Random(seed)
    trials = []
    for block, count in (("practice", practice_count), ("experiment", experimental_count)):
        if count < 0 or count % 4:
            raise ValueError("Each block size must be a nonnegative multiple of four.")
        combinations = [(color, side) for color in ("blue", "yellow") for side in ("left", "right")]
        items = combinations * (count // 4)
        rng.shuffle(items)
        first_number = len(trials) + 1
        trials.extend(Trial(first_number + i, block, color, side) for i, (color, side) in enumerate(items))
    return trials


def frame_count(duration_ms, refresh_hz):
    return max(1, int(duration_ms * refresh_hz / 1000 + 0.5))


def visual_phase(frame_index, stimulus_frames, response_frames):
    """No response argument: presentation never depends on button presses."""
    if frame_index < stimulus_frames:
        return "stimulus"
    if frame_index < response_frames:
        return "response"
    return "end"


def events_for_trial(trial, events):
    if trial.lower_ms is None or trial.upper_ms is None:
        return []
    # Boundaries are actual hardware timer replies. Message sequence disambiguates
    # events sharing a millisecond with a boundary and ties around optical onset.
    lower = (trial.lower_ms, trial.lower_sequence)
    upper = (trial.upper_ms, trial.upper_sequence)
    return [event for event in events if lower < (event.tpad_ms, event.sequence) < upper]


def score_trial(trial, events, config, session_id=""):
    row = {
        "session_id": session_id, "trial_number": trial.number, "block": trial.block,
        "stimulus_color": trial.color, "stimulus_side": trial.side,
        "congruency": trial.congruency, "correct_response": trial.correct_response,
        "actual_response": None, "accuracy": None, "opto_onset_tpad_ms": None,
        "opto_offset_tpad_ms": None, "button_press_tpad_ms": None,
        "button_release_tpad_ms": None, "rt_ms": None,
        "response_deadline_tpad_ms": None, "valid": False, "status": "invalid",
        "flags": "", "anticipatory_count": 0, "late_count": 0,
        "ignored_button_count": 0, "duplicate_count": 0,
        "lower_tpad_ms": trial.lower_ms, "upper_tpad_ms": trial.upper_ms,
        "lower_sequence": trial.lower_sequence, "upper_sequence": trial.upper_sequence,
        "stimulus_flip_host_s": trial.stimulus_flip_host_s,
        "offset_flip_host_s": trial.offset_flip_host_s,
        "visual_end_host_s": trial.visual_end_host_s,
        "completed": trial.completed,
    }
    invalid = list(trial.issues)
    flags = []
    if not trial.completed:
        invalid.append("incomplete_trial")
    if trial.lower_ms is None or trial.upper_ms is None:
        invalid.append("missing_hardware_boundary")
        row["flags"] = ";".join(sorted(set(invalid)))
        return row
    if trial.upper_ms <= trial.lower_ms:
        invalid.append("hardware_clock_discontinuity")
    assigned = events_for_trial(trial, events)
    row["duplicate_count"] = sum(event.duplicate for event in assigned)
    if row["duplicate_count"]:
        flags.append("duplicate_events")
    if any(event.unexpected for event in assigned):
        flags.append("unexpected_events")
    if trial.finalized_host_ns and any(event.arrival_monotonic_ns > trial.finalized_host_ns for event in assigned):
        invalid.append("event_after_grace")
    unique = [event for event in assigned if not event.duplicate]
    opto = [event for event in unique if event.channel == "C" and event.sensor == 1]
    onsets = [event for event in opto if event.edge == "P" and not event.unexpected]
    if not onsets:
        invalid.append("missing_optical_onset")
        row["flags"] = ";".join(sorted(set(invalid + flags)))
        return row
    onset = min(onsets, key=lambda event: event.sequence)
    onset_key = (onset.tpad_ms, onset.sequence)
    row["opto_onset_tpad_ms"] = onset.tpad_ms
    deadline = onset.tpad_ms + config["response_window_ms"]
    row["response_deadline_tpad_ms"] = deadline
    if len([event for event in opto if event.edge == "P"]) != 1:
        invalid.append("ambiguous_optical_onset")
    offsets = [event for event in opto if event.edge == "R" and
               (event.tpad_ms, event.sequence) > onset_key and not event.unexpected]
    if len(offsets) != 1:
        invalid.append("missing_or_ambiguous_optical_offset")
    else:
        row["opto_offset_tpad_ms"] = offsets[0].tpad_ms
        duration = offsets[0].tpad_ms - onset.tpad_ms
        if abs(duration - config["stimulus_ms"]) > config["optical_duration_tolerance_ms"]:
            invalid.append("optical_duration_outside_tolerance")
    if trial.upper_ms < deadline:
        invalid.append("drain_before_hardware_deadline")
    # XiD is sent in event order. Do not silently reorder a contradictory stream.
    if any(a.tpad_ms > b.tpad_ms for a, b in zip(unique, unique[1:])):
        invalid.append("hardware_event_order_uncertain")
    presses = [event for event in unique if event.channel == "A" and event.edge == "P"]
    eligible = []
    for event in presses:
        if event.sensor not in (1, 2):
            row["ignored_button_count"] += 1
            continue
        if (event.tpad_ms, event.sequence) < onset_key:
            row["anticipatory_count"] += 1
        elif event.tpad_ms > deadline:
            row["late_count"] += 1
        elif not event.unexpected:
            eligible.append(event)
    if row["anticipatory_count"]:
        flags.append("anticipatory_press")
    if row["late_count"]:
        flags.append("late_press")
    if row["ignored_button_count"]:
        flags.append("non_task_button")
    if eligible:
        response = min(eligible, key=lambda event: (event.tpad_ms, event.sequence))
        row["actual_response"] = response.sensor
        row["accuracy"] = int(response.sensor == trial.correct_response)
        row["button_press_tpad_ms"] = response.tpad_ms
        releases = [event for event in unique if event.channel == "A" and event.edge == "R"
                    and event.sensor == response.sensor and event.sequence > response.sequence
                    and event.tpad_ms >= response.tpad_ms and not event.unexpected]
        if releases:
            row["button_release_tpad_ms"] = releases[0].tpad_ms
        candidate_rt = response.tpad_ms - onset.tpad_ms
        if not invalid:
            row["rt_ms"] = candidate_rt
    elif not invalid:
        row["accuracy"] = 0
    row["valid"] = not invalid
    row["status"] = "invalid" if invalid else ("valid_response" if eligible else "valid_no_response")
    row["flags"] = ";".join(sorted(set(invalid + flags)))
    return row
