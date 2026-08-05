MAIN_PRE_LENGTH = 591.0
MAIN_MERGE_LENGTH = 89.0
MERGE_POINT_MAIN_POS = MAIN_PRE_LENGTH + MAIN_MERGE_LENGTH
RAMP_TOTAL_LENGTH = 322.0
OBSERVABLE_DISTANCE = 100.0
DEACTIVATE_DISTANCE = 185.0
STEP_LENGTH = 0.1


def infer_phase(vehicles):
    mv1 = vehicles["MV1"]
    mv2 = vehicles["MV2"]
    rv = vehicles["RV"]

    if mv1 is None or mv2 is None or rv is None:
        return "pending"

    rv_dist = rv["distance_to_merge"]
    mv2_dist = mv2["distance_to_merge"]

    if rv_dist is None or mv2_dist is None:
        return "pending"

    if rv_dist > DEACTIVATE_DISTANCE:
        return "approach"
    if rv_dist > OBSERVABLE_DISTANCE or mv2_dist > OBSERVABLE_DISTANCE:
        return "gap_creation"
    if rv["road_id"] in {"ramp_merge", "main_merge"} or mv2_dist > 0.0:
        return "speed_sync"
    return "release"


def infer_mv2_leader(vehicles):
    # Algorithm 2 initializes MV2.leader = MV1.
    # The actual switch to RV is now governed by flag2 inside the cloud controller.
    return "MV1"


def distance_to_merge(vehicle_state):
    road_id = vehicle_state["road_id"]
    lane_pos = vehicle_state["lane_pos"]

    if road_id.startswith(":"):
        return 0.0
    if road_id == "main_pre":
        return MAIN_PRE_LENGTH - lane_pos + MAIN_MERGE_LENGTH
    if road_id == "main_merge":
        return max(0.0, MAIN_MERGE_LENGTH - lane_pos)
    if road_id == "main_out":
        return 0.0
    if road_id == "ramp_pre":
        return RAMP_TOTAL_LENGTH - lane_pos
    if road_id == "ramp_merge":
        return max(0.0, MAIN_MERGE_LENGTH - lane_pos)
    return None


def distance_to_interacting_zone(distance_to_merge_value):
    if distance_to_merge_value is None:
        return None
    return distance_to_merge_value - OBSERVABLE_DISTANCE


def build_vehicle_state(traci, veh_id):
    if veh_id not in traci.vehicle.getIDList():
        return None

    state = {
        "id": veh_id,
        "speed": traci.vehicle.getSpeed(veh_id),
        "road_id": traci.vehicle.getRoadID(veh_id),
        "lane_id": traci.vehicle.getLaneID(veh_id),
        "lane_pos": traci.vehicle.getLanePosition(veh_id),
        "x": traci.vehicle.getPosition(veh_id)[0],
        "y": traci.vehicle.getPosition(veh_id)[1],
    }
    state["distance_to_merge"] = distance_to_merge(state)
    state["distance_to_interacting_zone"] = distance_to_interacting_zone(
        state["distance_to_merge"]
    )
    if state["distance_to_merge"] is None:
        state["projected_longitudinal_position"] = None
    else:
        state["projected_longitudinal_position"] = (
            MERGE_POINT_MAIN_POS - state["distance_to_merge"]
        )
    return state


def build_scenario_state(traci, vehicle_ids):
    vehicles = {}
    for veh_id in vehicle_ids:
        vehicles[veh_id] = build_vehicle_state(traci, veh_id)

    all_present = all(vehicles[veh_id] is not None for veh_id in vehicle_ids)
    sim_time = traci.simulation.getTime()
    phase = infer_phase(vehicles)
    relationships = {}

    if all_present:
        mv1 = vehicles["MV1"]
        mv2 = vehicles["MV2"]
        rv = vehicles["RV"]
        leader_for_mv2 = infer_mv2_leader(vehicles)
        relationships = {
            "mainline_gap": mv1["x"] - mv2["x"],
            "rv_to_mv1": mv1["x"] - rv["x"],
            "rv_to_mv2": rv["x"] - mv2["x"],
            "rv_merge_dist": rv["distance_to_merge"],
            "mv2_merge_dist": mv2["distance_to_merge"],
            "mv1_d2i": mv1["distance_to_interacting_zone"],
            "rv_d2i": rv["distance_to_interacting_zone"],
            "leader_for_mv2": leader_for_mv2,
        }

    return {
        "time": sim_time,
        "phase": phase,
        "all_present": all_present,
        "vehicles": vehicles,
        "relationships": relationships,
        "merge_point_main_pos": MERGE_POINT_MAIN_POS,
        "ramp_total_length": RAMP_TOTAL_LENGTH,
        "observable_distance": OBSERVABLE_DISTANCE,
        "deactivate_distance": DEACTIVATE_DISTANCE,
        "step_length": STEP_LENGTH,
    }
