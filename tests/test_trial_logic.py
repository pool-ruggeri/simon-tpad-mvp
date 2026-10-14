import unittest

from tpad_serial import Event
from trial_logic import Trial, events_for_trial, make_trials, score_trial

CONFIG = {"response_window_ms": 1500, "stimulus_ms": 500, "optical_duration_tolerance_ms": 50}


def event(sequence, channel, edge, sensor, stamp, **kwargs):
    return Event(sequence, channel, edge, sensor, stamp, 100, "", **kwargs)


def completed_trial(number=1, lower=500, upper=3000, lower_seq=0, upper_seq=100):
    return Trial(number, "experiment", "blue", "left", lower, upper, lower_seq, upper_seq, completed=True)


class TrialTests(unittest.TestCase):
    def score(self, middle=(), trial=None):
        events = [event(1, "C", "P", 1, 1000), *middle, event(20, "C", "R", 1, 1500)]
        events.sort(key=lambda item: item.sequence)
        return score_trial(trial or completed_trial(), events, CONFIG)

    def test_reproducible_balanced_blocks_unique_trial_numbers(self):
        trials = make_trials(4, 16, 42)
        self.assertEqual(trials, make_trials(4, 16, 42))
        self.assertEqual([trial.number for trial in trials], list(range(1, 21)))
        for block, repeats in (("practice", 1), ("experiment", 4)):
            items = [(trial.color, trial.side) for trial in trials if trial.block == block]
            for combination in (("blue", "left"), ("blue", "right"), ("yellow", "left"), ("yellow", "right")):
                self.assertEqual(items.count(combination), repeats)
        with self.assertRaises(ValueError):
            make_trials(3, 16, 42)

    def test_congruency_and_mapping_all_conditions(self):
        for color, side, response, congruency in (
            ("blue", "left", 1, "congruent"), ("blue", "right", 1, "incongruent"),
            ("yellow", "left", 2, "incongruent"), ("yellow", "right", 2, "congruent"),
        ):
            trial = Trial(1, "practice", color, side)
            self.assertEqual(trial.correct_response, response)
            self.assertEqual(trial.congruency, congruency)

    def test_rt_uses_only_integer_hardware_timestamps(self):
        trial = completed_trial()
        trial.stimulus_flip_host_s = 900000.25
        row = self.score([event(2, "A", "P", 1, 1200), event(3, "A", "R", 1, 1250)], trial)
        self.assertEqual(row["rt_ms"], 200)
        self.assertIs(type(row["rt_ms"]), int)
        self.assertEqual(row["button_release_tpad_ms"], 1250)
        self.assertEqual(row["accuracy"], 1)
        self.assertTrue(row["valid"])

    def test_first_eligible_press_determines_accuracy(self):
        row = self.score([event(2, "A", "P", 2, 1150), event(3, "A", "P", 1, 1200)])
        self.assertEqual((row["actual_response"], row["accuracy"], row["rt_ms"]), (2, 0, 150))

    def test_anticipatory_and_same_millisecond_before_onset_are_excluded(self):
        events = [event(1, "A", "P", 1, 999), event(2, "A", "P", 2, 1000),
                  event(3, "C", "P", 1, 1000), event(4, "C", "R", 1, 1500)]
        row = score_trial(completed_trial(), events, CONFIG)
        self.assertEqual(row["anticipatory_count"], 2)
        self.assertEqual(row["status"], "valid_no_response")
        self.assertIsNone(row["rt_ms"])

    def test_window_end_inclusive_and_one_millisecond_late_excluded(self):
        row = self.score([event(21, "A", "P", 1, 2500)])
        self.assertEqual(row["rt_ms"], 1500)
        late = self.score([event(21, "A", "P", 1, 2501)])
        self.assertEqual(late["late_count"], 1)
        self.assertIsNone(late["rt_ms"])
        self.assertEqual(late["status"], "valid_no_response")

    def test_buttons_three_and_four_are_logged_but_not_task_responses(self):
        row = self.score([event(2, "A", "P", 3, 1100), event(3, "A", "P", 4, 1150), event(4, "A", "P", 1, 1200)])
        self.assertEqual(row["ignored_button_count"], 2)
        self.assertEqual(row["rt_ms"], 200)

    def test_missing_onset_never_uses_host_flip_or_response_as_onset(self):
        trial = completed_trial()
        trial.stimulus_flip_host_s = 1.0
        row = score_trial(trial, [event(2, "A", "P", 1, 1200)], CONFIG)
        self.assertFalse(row["valid"])
        self.assertIsNone(row["rt_ms"])
        self.assertIsNone(row["opto_onset_tpad_ms"])
        self.assertIn("missing_optical_onset", row["flags"])

    def test_duplicate_does_not_change_first_response(self):
        row = self.score([event(2, "A", "P", 1, 1200), event(3, "A", "P", 1, 1200, duplicate=True)])
        self.assertTrue(row["valid"])
        self.assertEqual(row["duplicate_count"], 1)
        self.assertEqual(row["rt_ms"], 200)

    def test_delayed_arrival_assigned_by_hardware_boundaries(self):
        first = completed_trial(1, 500, 3000, 0, 5)
        second = completed_trial(2, 3500, 6000, 6, 12)
        # First response was parsed after the second optical onset. It still has
        # the first trial's hardware timestamp and must never score trial two.
        events = [event(1, "C", "P", 1, 1000), event(2, "C", "R", 1, 1500),
                  event(7, "C", "P", 1, 4000), event(8, "A", "P", 1, 1200),
                  event(9, "C", "R", 1, 4500)]
        row = score_trial(first, events, CONFIG)
        self.assertEqual(row["actual_response"], 1)
        self.assertFalse(row["valid"])
        self.assertIn("hardware_event_order_uncertain", row["flags"])
        self.assertIsNone(score_trial(second, events, CONFIG)["rt_ms"])
        self.assertEqual([e.tpad_ms for e in events_for_trial(first, events)], [1000, 1500, 1200])

    def test_delayed_fifo_messages_have_correct_rt_before_grace_ends(self):
        first = completed_trial(1, 500, 3000, 0, 5)
        first.finalized_host_ns = 1000
        events = [Event(1, "C", "P", 1, 1000, 990, ""),
                  Event(2, "A", "P", 1, 1200, 990, ""),
                  Event(3, "C", "R", 1, 1500, 990, "")]
        self.assertEqual(score_trial(first, events, CONFIG)["rt_ms"], 200)

    def test_missing_onset_does_not_shift_later_trial(self):
        first = completed_trial(1, 500, 3000, 0, 5)
        second = completed_trial(2, 3500, 6000, 6, 12)
        events = [event(1, "A", "P", 1, 1200), event(7, "C", "P", 1, 4000),
                  event(8, "A", "P", 1, 4200), event(9, "C", "R", 1, 4500)]
        self.assertFalse(score_trial(first, events, CONFIG)["valid"])
        self.assertEqual(score_trial(second, events, CONFIG)["rt_ms"], 200)

    def test_no_response_is_valid_omission_with_empty_rt(self):
        row = self.score()
        self.assertEqual((row["status"], row["accuracy"], row["rt_ms"]), ("valid_no_response", 0, None))

    def test_missing_offset_chatter_or_wrong_duration_invalidates_rt(self):
        cases = [
            [event(1, "C", "P", 1, 1000), event(2, "A", "P", 1, 1200)],
            [event(1, "C", "P", 1, 1000), event(2, "C", "R", 1, 1020),
             event(3, "C", "P", 1, 1030), event(4, "A", "P", 1, 1200), event(5, "C", "R", 1, 1500)],
            [event(1, "C", "P", 1, 1000), event(2, "A", "P", 1, 1200), event(3, "C", "R", 1, 1800)],
        ]
        for events in cases:
            with self.subTest(events=events):
                row = score_trial(completed_trial(), events, CONFIG)
                self.assertFalse(row["valid"])
                self.assertIsNone(row["rt_ms"])

    def test_clock_reset_insufficient_drain_and_incomplete_are_invalid(self):
        for trial in (completed_trial(upper=400), completed_trial(upper=2000), Trial(1, "experiment", "blue", "left")):
            with self.subTest(trial=trial):
                row = self.score([event(2, "A", "P", 1, 1200)], trial)
                self.assertFalse(row["valid"])
                self.assertIsNone(row["rt_ms"])

    def test_arrival_after_grace_is_retained_but_flagged(self):
        trial = completed_trial()
        trial.finalized_host_ns = 90
        row = self.score([event(2, "A", "P", 1, 1200)], trial)
        self.assertFalse(row["valid"])
        self.assertEqual(row["actual_response"], 1)
        self.assertIn("event_after_grace", row["flags"])


if __name__ == "__main__":
    unittest.main()
