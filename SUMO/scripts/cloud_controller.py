class CloudController:
    def __init__(self, params=None):
        self.role_map = {
            "leader": "MV1",
            "follower": "MV2",
            "ramp_vehicle": "RV",
        }
        self.flag2 = 0
        self.activation_counter = 0.0
        self.deactivation_counter = 0.0
        self.gap_phase_elapsed = 0.0
        self.last_phase = None
        self.p1_accel_threshold = 0.5
        self.p2_activate_ratio = 0.6
        self.p3_deactivate_ratio = 0.6
        self.speed_limit = 20.0
        self.max_accel = 3.0
        self.min_accel = -3.0
        self.tau = 0.088
        self.vehicle_length = 5.0
        self.k_r = 0.18
        self.k_m1 = 0.20
        self.k_m2 = 0.22
        self.gamma_r = 1.0
        self.gamma_m1 = 1.1
        self.gamma_m2 = 1.2
        self.t_gap_r = 1.2
        self.t_gap_m = 1.0
        self.advisory_update_period = 1.0 / 3.0
        self.last_advisory_update_time = None
        self.cached_commands = None
        self.cached_control_state = None
        self.last_advisory_speed = {"MV1": 18.0, "MV2": 18.0, "RV": 16.0}
        self.predicted_tracking_error = {"MV1": 0.0, "MV2": 0.0, "RV": 0.0}
        self.error_smoothing = 0.35
        self.compensation_gain = 0.6
        self.lookup_gamma_cache = {}
        self.release_hold_duration = 2.0
        self.release_hold_elapsed = 0.0
        self._apply_params(params or {})

    def _apply_params(self, params):
        for key, value in params.items():
            if not hasattr(self, key):
                raise ValueError(f"Unknown controller parameter: {key}")
            setattr(self, key, value)

    def _on_phase_change(self, phase):
        phase_changed = phase != self.last_phase
        if phase_changed and phase == "gap_creation":
            self.activation_counter = 0.0
            self.deactivation_counter = 0.0
            self.gap_phase_elapsed = 0.0
            self.flag2 = 0
            self.lookup_gamma_cache = {}
        if phase_changed and phase == "release":
            self.release_hold_elapsed = 0.0
        self.last_phase = phase
        return phase_changed

    def _interacting_zone_ready(self, relationships):
        mv1_d2i = relationships.get("mv1_d2i")
        rv_d2i = relationships.get("rv_d2i")
        if mv1_d2i is None or rv_d2i is None:
            return False
        return mv1_d2i <= 0.0 and rv_d2i <= 0.0

    def _release_commands(self):
        return {
            "MV1": {"target_speed": -1},
            "MV2": {"target_speed": -1},
            "RV": {"target_speed": -1},
        }

    def _release_hold_commands(self):
        return {
            "MV1": {"target_speed": 18.0, "raw_target_speed": 18.0, "transition_time": 1.0},
            "MV2": {"target_speed": 17.8, "raw_target_speed": 17.8, "transition_time": 1.0},
            "RV": {"target_speed": 18.0, "raw_target_speed": 18.0, "transition_time": 1.0},
        }

    def _clamp(self, value, lower, upper):
        return max(lower, min(value, upper))

    def _consensus_target_speed(self, ego, leader, gain, gamma, t_gap, dt):
        if ego is None or leader is None:
            return None, None

        r_i = ego["projected_longitudinal_position"]
        r_j = leader["projected_longitudinal_position"]
        v_i = ego["speed"]
        v_j = leader["speed"]

        if r_i is None or r_j is None:
            return None, None

        spacing_term = r_i - r_j + self.vehicle_length + v_i * (t_gap + self.tau)
        speed_term = v_i - v_j
        a_ref = -gain * (spacing_term + gamma * speed_term)
        a_ref = self._clamp(a_ref, self.min_accel, self.max_accel)
        target_speed = v_i + a_ref * dt
        target_speed = self._clamp(target_speed, 0.0, self.speed_limit)
        return target_speed, a_ref

    def _lookup_gamma(self, cache_key, ego, leader, base_gamma):
        cached = self.lookup_gamma_cache.get(cache_key)
        if cached is not None:
            return cached

        if ego is None or leader is None:
            gamma = base_gamma
        else:
            r_i = ego.get("projected_longitudinal_position")
            r_j = leader.get("projected_longitudinal_position")
            v_i = ego.get("speed")
            v_j = leader.get("speed")

            if None in (r_i, r_j, v_i, v_j):
                gamma = base_gamma
            else:
                initial_gap = abs(r_j - r_i)
                speed_delta = abs(v_j - v_i)
                gamma = base_gamma
                if initial_gap < 40.0:
                    gamma += 0.25
                elif initial_gap > 90.0:
                    gamma -= 0.10
                if speed_delta > 4.0:
                    gamma += 0.20
                elif speed_delta < 1.5:
                    gamma -= 0.05
                gamma = self._clamp(gamma, 0.7, 1.8)

        self.lookup_gamma_cache[cache_key] = gamma
        return gamma

    def _compensate_advisory_speed(self, veh_id, raw_target_speed, current_speed):
        last_advisory = self.last_advisory_speed[veh_id]
        observed_error = last_advisory - current_speed
        predicted_error = (
            self.error_smoothing * observed_error
            + (1.0 - self.error_smoothing) * self.predicted_tracking_error[veh_id]
        )
        self.predicted_tracking_error[veh_id] = predicted_error
        advisory_speed = raw_target_speed + self.compensation_gain * predicted_error
        advisory_speed = self._clamp(advisory_speed, 0.0, self.speed_limit)
        self.last_advisory_speed[veh_id] = advisory_speed
        return advisory_speed, predicted_error

    def _update_flag2(self, state, rv_target_speed):
        dt = state.get("step_length", 0.1)
        relationships = state["relationships"]
        if not self._interacting_zone_ready(relationships):
            return {
                "flag2": self.flag2,
                "rv_advisory_accel": None,
                "rv_advisory_speed_exceeded": None,
                "activation_ratio": None,
                "deactivation_ratio": None,
                "gap_phase_elapsed": self.gap_phase_elapsed,
                "monitor_active": False,
            }

        self.gap_phase_elapsed += dt
        elapsed = max(self.gap_phase_elapsed, dt)
        rv_speed = state["vehicles"]["RV"]["speed"]
        rv_advisory_accel = rv_target_speed - rv_speed
        rv_advisory_speed_exceeded = rv_target_speed > self.speed_limit

        # Algorithm 3 monitors whether RV can feasibly track the advisory speed.
        if rv_advisory_accel > self.p1_accel_threshold or rv_advisory_speed_exceeded:
            self.deactivation_counter += dt
        else:
            self.activation_counter += dt

        activation_ratio = self.activation_counter / elapsed
        deactivation_ratio = self.deactivation_counter / elapsed

        if self.flag2 != -1 and activation_ratio >= self.p2_activate_ratio:
            self.flag2 = 1
        if deactivation_ratio >= self.p3_deactivate_ratio:
            self.flag2 = -1

        return {
            "flag2": self.flag2,
            "rv_advisory_accel": rv_advisory_accel,
            "rv_advisory_speed_exceeded": rv_advisory_speed_exceeded,
            "activation_ratio": activation_ratio,
            "deactivation_ratio": deactivation_ratio,
            "gap_phase_elapsed": elapsed,
            "monitor_active": True,
        }

    def _approach_commands(self, state, relationships):
        vehicles = state["vehicles"]
        dt = state.get("step_length", 0.1)
        rv_gamma = self._lookup_gamma("RV_to_MV1", vehicles["RV"], vehicles["MV1"], self.gamma_r)
        rv_raw_speed, rv_accel = self._consensus_target_speed(
            vehicles["RV"], vehicles["MV1"], self.k_r, rv_gamma, self.t_gap_r, dt
        )
        if rv_raw_speed is None:
            rv_raw_speed = 16.0 if relationships["rv_merge_dist"] > 210.0 else 16.5
        rv_speed, rv_error = self._compensate_advisory_speed(
            "RV", rv_raw_speed, vehicles["RV"]["speed"]
        )
        return {
            "MV1": {"target_speed": 18.0, "raw_target_speed": 18.0, "transition_time": 1.0},
            "MV2": {"target_speed": 18.0, "raw_target_speed": 18.0, "transition_time": 1.0},
            "RV": {
                "target_speed": rv_speed,
                "raw_target_speed": rv_raw_speed,
                "transition_time": 1.0,
                "a_ref": rv_accel,
                "predicted_error": rv_error,
                "gamma": rv_gamma,
            },
        }

    def _gap_creation_commands(self, state, relationships):
        vehicles = state["vehicles"]
        dt = state.get("step_length", 0.1)
        mainline_gap = relationships["mainline_gap"]
        rv_to_mv2 = relationships["rv_to_mv2"]
        rv_merge_dist = relationships["rv_merge_dist"]
        leader_for_mv2 = relationships["leader_for_mv2"]
        rv_gamma = self._lookup_gamma("RV_to_MV1", vehicles["RV"], vehicles["MV1"], self.gamma_r)
        rv_raw_speed, rv_accel = self._consensus_target_speed(
            vehicles["RV"], vehicles["MV1"], self.k_r, rv_gamma, self.t_gap_r, dt
        )
        if rv_raw_speed is None:
            rv_raw_speed = 17.0

        mv2_leader_vehicle = vehicles["MV1"] if leader_for_mv2 == "MV1" else vehicles["RV"]
        mv2_gain = self.k_m1 if leader_for_mv2 == "MV1" else self.k_m2
        mv2_base_gamma = self.gamma_m1 if leader_for_mv2 == "MV1" else self.gamma_m2
        mv2_gamma = self._lookup_gamma(
            f"MV2_to_{leader_for_mv2}", vehicles["MV2"], mv2_leader_vehicle, mv2_base_gamma
        )
        mv2_raw_speed, mv2_accel = self._consensus_target_speed(
            vehicles["MV2"], mv2_leader_vehicle, mv2_gain, mv2_gamma, self.t_gap_m, dt
        )
        if mv2_raw_speed is None:
            mv2_raw_speed = 14.0

        # Keep some rule-based shaping around the consensus core to preserve the intended gap.
        if leader_for_mv2 == "MV1":
            if mainline_gap < 55.0:
                mv2_raw_speed = min(mv2_raw_speed, 13.5)
            elif mainline_gap > 75.0:
                mv2_raw_speed = max(mv2_raw_speed, 15.0)
        else:
            if rv_to_mv2 < 5.0:
                mv2_raw_speed = min(mv2_raw_speed, 13.5)
            elif rv_to_mv2 > 20.0:
                mv2_raw_speed = max(mv2_raw_speed, 15.0)

        if rv_to_mv2 < 10.0:
            rv_raw_speed = min(rv_raw_speed, 16.5)
        if rv_merge_dist < 100.0:
            rv_raw_speed = max(rv_raw_speed, 17.5)

        mv2_speed, mv2_error = self._compensate_advisory_speed(
            "MV2", mv2_raw_speed, vehicles["MV2"]["speed"]
        )
        rv_speed, rv_error = self._compensate_advisory_speed(
            "RV", rv_raw_speed, vehicles["RV"]["speed"]
        )

        return {
            "MV1": {"target_speed": 18.0, "raw_target_speed": 18.0, "transition_time": 1.0},
            "MV2": {
                "target_speed": mv2_speed,
                "raw_target_speed": mv2_raw_speed,
                "transition_time": 1.0,
                "a_ref": mv2_accel,
                "predicted_error": mv2_error,
                "gamma": mv2_gamma,
            },
            "RV": {
                "target_speed": rv_speed,
                "raw_target_speed": rv_raw_speed,
                "transition_time": 1.0,
                "a_ref": rv_accel,
                "predicted_error": rv_error,
                "gamma": rv_gamma,
            },
        }

    def _speed_sync_commands(self, state, relationships):
        vehicles = state["vehicles"]
        dt = state.get("step_length", 0.1)
        rv_to_mv2 = relationships["rv_to_mv2"]
        mv2_merge_dist = relationships["mv2_merge_dist"]
        leader_for_mv2 = relationships["leader_for_mv2"]
        rv_gamma = self._lookup_gamma("RV_to_MV1", vehicles["RV"], vehicles["MV1"], self.gamma_r)
        rv_raw_speed, rv_accel = self._consensus_target_speed(
            vehicles["RV"], vehicles["MV1"], self.k_r, rv_gamma, self.t_gap_r, dt
        )
        if rv_raw_speed is None:
            rv_raw_speed = 18.0

        mv2_leader_vehicle = vehicles["RV"] if leader_for_mv2 == "RV" else vehicles["MV1"]
        mv2_gain = self.k_m2 if leader_for_mv2 == "RV" else self.k_m1
        mv2_base_gamma = self.gamma_m2 if leader_for_mv2 == "RV" else self.gamma_m1
        mv2_gamma = self._lookup_gamma(
            f"MV2_to_{leader_for_mv2}", vehicles["MV2"], mv2_leader_vehicle, mv2_base_gamma
        )
        mv2_raw_speed, mv2_accel = self._consensus_target_speed(
            vehicles["MV2"], mv2_leader_vehicle, mv2_gain, mv2_gamma, self.t_gap_m, dt
        )
        if mv2_raw_speed is None:
            mv2_raw_speed = 18.0

        if leader_for_mv2 == "RV" and rv_to_mv2 < 5.0:
            mv2_raw_speed = min(mv2_raw_speed, 17.5)
            rv_raw_speed = min(rv_raw_speed, 17.5)
        if mv2_merge_dist < 25.0:
            mv2_raw_speed = min(mv2_raw_speed, 17.8)

        mv2_speed, mv2_error = self._compensate_advisory_speed(
            "MV2", mv2_raw_speed, vehicles["MV2"]["speed"]
        )
        rv_speed, rv_error = self._compensate_advisory_speed(
            "RV", rv_raw_speed, vehicles["RV"]["speed"]
        )

        return {
            "MV1": {"target_speed": 18.0, "raw_target_speed": 18.0, "transition_time": 1.0},
            "MV2": {
                "target_speed": mv2_speed,
                "raw_target_speed": mv2_raw_speed,
                "transition_time": 1.0,
                "a_ref": mv2_accel,
                "predicted_error": mv2_error,
                "gamma": mv2_gamma,
            },
            "RV": {
                "target_speed": rv_speed,
                "raw_target_speed": rv_raw_speed,
                "transition_time": 1.0,
                "a_ref": rv_accel,
                "predicted_error": rv_error,
                "gamma": rv_gamma,
            },
        }

    def _should_refresh_advisory(self, sim_time, phase_changed):
        if phase_changed:
            return True
        if self.last_advisory_update_time is None:
            return True
        return (sim_time - self.last_advisory_update_time) >= (
            self.advisory_update_period - 1e-9
        )

    def _build_control_state(self, commands, extra=None):
        control_state = {
            "raw_target_speeds": {
                veh_id: commands[veh_id].get("raw_target_speed")
                for veh_id in commands
            },
            "advisory_target_speeds": {
                veh_id: commands[veh_id].get("target_speed")
                for veh_id in commands
            },
            "predicted_errors": {
                veh_id: commands[veh_id].get("predicted_error") for veh_id in commands
            },
            "gamma_values": {
                veh_id: commands[veh_id].get("gamma") for veh_id in commands
            },
        }
        if extra:
            control_state.update(extra)
        return control_state

    def compute_commands(self, state):
        phase = state["phase"]
        relationships = state["relationships"]
        sim_time = state["time"]
        phase_changed = self._on_phase_change(phase)

        if (
            not self._should_refresh_advisory(sim_time, phase_changed)
            and self.cached_commands is not None
            and self.cached_control_state is not None
        ):
            state["control_state"] = dict(self.cached_control_state)
            state["control_state"]["advisory_refresh"] = False
            return self.cached_commands

        if phase == "approach":
            commands = self._approach_commands(state, relationships)
            state["control_state"] = self._build_control_state(
                commands,
                {
                    "flag2": self.flag2,
                    "leader_for_mv2": "MV1",
                    "monitor_active": False,
                    "advisory_refresh": True,
                },
            )
            self.cached_commands = commands
            self.cached_control_state = dict(state["control_state"])
            self.last_advisory_update_time = sim_time
            return commands

        if phase == "gap_creation":
            preview_commands = self._gap_creation_commands(state, relationships)
            monitor = self._update_flag2(
                state,
                preview_commands["RV"]["target_speed"],
            )
            leader_for_mv2 = "RV" if monitor["flag2"] == 1 else "MV1"
            relationships["leader_for_mv2"] = leader_for_mv2
            commands = self._gap_creation_commands(state, relationships)
            state["control_state"] = self._build_control_state(
                commands,
                {
                    "flag2": monitor["flag2"],
                    "leader_for_mv2": leader_for_mv2,
                    "rv_advisory_accel": monitor["rv_advisory_accel"],
                    "rv_advisory_speed_exceeded": monitor["rv_advisory_speed_exceeded"],
                    "activation_ratio": monitor["activation_ratio"],
                    "deactivation_ratio": monitor["deactivation_ratio"],
                    "gap_phase_elapsed": monitor["gap_phase_elapsed"],
                    "monitor_active": monitor["monitor_active"],
                    "advisory_refresh": True,
                },
            )
            self.cached_commands = commands
            self.cached_control_state = dict(state["control_state"])
            self.last_advisory_update_time = sim_time
            return commands

        if phase == "speed_sync":
            relationships["leader_for_mv2"] = "RV" if self.flag2 == 1 else "MV1"
            commands = self._speed_sync_commands(state, relationships)
            state["control_state"] = self._build_control_state(
                commands,
                {
                    "flag2": self.flag2,
                    "leader_for_mv2": relationships["leader_for_mv2"],
                    "gap_phase_elapsed": self.gap_phase_elapsed,
                    "monitor_active": self._interacting_zone_ready(relationships),
                    "advisory_refresh": True,
                },
            )
            self.cached_commands = commands
            self.cached_control_state = dict(state["control_state"])
            self.last_advisory_update_time = sim_time
            return commands

        self.release_hold_elapsed += state.get("step_length", 0.1)
        if self.release_hold_elapsed < self.release_hold_duration:
            commands = self._release_hold_commands()
            state["control_state"] = self._build_control_state(
                commands,
                {
                    "flag2": self.flag2,
                    "leader_for_mv2": relationships.get("leader_for_mv2", "RV"),
                    "monitor_active": False,
                    "advisory_refresh": True,
                    "release_hold_active": True,
                    "release_hold_elapsed": self.release_hold_elapsed,
                },
            )
        else:
            self.flag2 = -1
            commands = self._release_commands()
            state["control_state"] = {
                "flag2": self.flag2,
                "leader_for_mv2": relationships.get("leader_for_mv2", "RV"),
                "monitor_active": False,
                "advisory_refresh": True,
                "release_hold_active": False,
                "release_hold_elapsed": self.release_hold_elapsed,
            }
        self.cached_commands = commands
        self.cached_control_state = dict(state["control_state"])
        self.last_advisory_update_time = sim_time
        return commands
