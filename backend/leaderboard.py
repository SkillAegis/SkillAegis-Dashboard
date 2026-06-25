#!/usr/bin/env python3
from collections import defaultdict
import time
import backend.db as db
from backend.appConfig import leaderboard_settings
from backend.trophies import GrinderTrophy, BounceBackTrophy, MessengerTrophy, SpammerTrophy

ALL_TROPHIES = [
    GrinderTrophy.GrinderTrophy(),
    BounceBackTrophy.BounceBackTrophy(),
    MessengerTrophy.MessengerTrophy(),
    SpammerTrophy.SpammerTrophy(),
    # Other trophies can be defined in individual scenarios
]


def get_score_for_task_completion(tasks_completion: dict) -> int:
    score = 0
    for inject_uuid, completed in tasks_completion.items():
        if not completed:
            continue
        inject = db.INJECT_BY_UUID[inject_uuid]
        try:
            for inject_eval in inject["inject_evaluation"]:
                score += inject_eval["score_range"][1]
        except KeyError:
            pass
    return score


def get_completed_task_count(tasks_completion: dict) -> int:
    count = 0
    for inject_uuid, completed in tasks_completion.items():
        if completed:
            count += 1
    return count


def get_hall_of_fame(selected_exercices: list, completion_for_users: dict) -> list:
    total_score = get_total_score_for_users(selected_exercices, completion_for_users)
    sorted_by_score = sorted(total_score, key=lambda x: x['score'], reverse=True)
    elligible_score = get_elligible_score_for_leaderboard(selected_exercices)
    hall_of_fame = [x for x in sorted_by_score if x["score"] >= elligible_score]
    return hall_of_fame[:9]


def get_time_on_fire(selected_exercices, completion_for_users) -> list:
    time_on_fire = get_time_on_fire_for_users(selected_exercices, completion_for_users)
    sorted_by_time_on_fire = sorted(time_on_fire, key=lambda x: x["time_on_fire"], reverse=True)

    total_score = get_total_score_for_users(selected_exercices, completion_for_users)
    score_by_user = {entry["user_id"]: entry["score"] for entry in total_score}
    elligible_score = get_elligible_score_for_leaderboard(selected_exercices)

    task_amount = 0
    for exec_uuid in selected_exercices:
        task_amount += len(db.EXERCISES_STATUS[exec_uuid]["tasks"])
    min_elligible_time = leaderboard_settings["time_one_fire_window_sec"] * task_amount

    time_on_fire = [x for x in sorted_by_time_on_fire if x['time_on_fire'] >= min_elligible_time or score_by_user[x["user_id"]] >= elligible_score]

    return time_on_fire[:9]


def get_speed_runner(selected_exercices: list, completion_for_users: dict) -> list:
    speedrunner_scores = get_speedrunner_score_for_users(selected_exercices, completion_for_users)
    sorted_by_speedrunner_score = sorted(speedrunner_scores, key=lambda x: x["speedrunner_score"], reverse=True)
    total_score = get_total_score_for_users(selected_exercices, completion_for_users)
    score_by_user = { entry["user_id"]: entry["score"] for entry in total_score }
    elligible_score = get_elligible_score_for_leaderboard(selected_exercices)
    speedrunner_scores = [x for x in sorted_by_speedrunner_score if score_by_user[x["user_id"]] >= elligible_score]
    return speedrunner_scores[:9]


def get_speedrunner_score_ceiling(selected_exercices: list) -> float:
    """Speedrunner score of a full clean run — every task completed, accruing the
    exercise's max_score. This is the theoretical ceiling the dashboard scales its
    0-10 Speed Index against, mirroring how time-on-fire derives a ceiling from
    (task_amount x fire_window). Returns 0 when there is nothing to complete."""
    volume_boost = leaderboard_settings["speedrunner_volume_boost"]
    speed_boost = leaderboard_settings["speedrunner_speed_boost"]
    task_amount = 0
    max_score = 0
    for exec_uuid in selected_exercices:
        task_amount += len(db.EXERCISES_STATUS[exec_uuid]["tasks"])
        max_score += db.EXERCISES_STATUS[exec_uuid]["max_score"]
    if task_amount == 0 or max_score == 0:
        return 0
    return (task_amount ** volume_boost) / (max_score ** speed_boost)


def get_user_stats(selected_exercices: list, completion_for_users: dict) -> dict:
    return {
        "hall_of_fame": get_hall_of_fame(selected_exercices, completion_for_users),
        "time_on_fire": get_time_on_fire(selected_exercices, completion_for_users),
        "speed_runner": get_speed_runner(selected_exercices, completion_for_users),
        "trophies": get_trophies(selected_exercices, completion_for_users),
        "settings": {
            "time_on_fire_window_sec": leaderboard_settings["time_one_fire_window_sec"],
            "speedrunner_score_ceiling": get_speedrunner_score_ceiling(selected_exercices),
        },
    }


def get_user_status(user_id: int, selected_exercices: list, completion_for_users: dict) -> dict:
    user_stats = get_user_stats(selected_exercices, completion_for_users)
    users_on_fire = get_users_on_fire(selected_exercices, completion_for_users)
    users_trophies = get_trophies(selected_exercices, completion_for_users)
    collected_trophies = []
    for trophy in users_trophies.values():
        for user in trophy['users']:
            if user['user_id'] == user_id:
                collected_trophies.append(trophy['metadata'])

    status = {
        "is_on_fire": user_id in [entry['user_id'] for entry in users_on_fire],
        "on_fire_last_interval": next((entry['time_on_fire_interval'] for entry in users_on_fire if entry['user_id'] == user_id), None),
        "is_on_fire_leaderboard": user_id in [entry['user_id'] for entry in user_stats["time_on_fire"]],
        "is_on_all_house_fame": user_id in [entry['user_id'] for entry in user_stats["hall_of_fame"]],
        "is_speed_runner": user_id in [entry['user_id'] for entry in user_stats["speed_runner"]],
        "trophies": collected_trophies,
    }
    return status


def get_trophies(selected_exercices: list, completion_for_users: dict) -> dict:

    user_trophies = {}
    for trophy in ALL_TROPHIES:
        trophy_d = trophy.to_dict()
        user_trophies[trophy_d["id"]] = {
            "metadata": trophy_d,
            "users": trophy.is_earned_for_users(selected_exercices, completion_for_users),
        }

    return user_trophies


def get_elligible_score_for_leaderboard(selected_exercices: list) -> int:
    max_score = 0
    for exec_uuid in selected_exercices:
        max_score += db.EXERCISES_STATUS[exec_uuid]["max_score"]
    elligible_score = max_score / 2
    return elligible_score

def get_total_score_for_users(selected_exercices: list, completion_for_users: dict) -> list:
    total_score_per_user = defaultdict(int)
    for user_id in completion_for_users.keys():
        if user_id not in db.USER_ID_TO_EMAIL_MAPPING:
            print("unknown user id", user_id)
            continue
        for exec_uuid, tasks_completion in completion_for_users[user_id].items():
            if exec_uuid in selected_exercices:
                total_score_per_user[user_id] += get_score_for_task_completion(tasks_completion)

    total_score = []
    for user_id, score in total_score_per_user.items():
        total_score.append({
            "user_id": user_id,
            "email": db.USER_ID_TO_EMAIL_MAPPING[user_id],
            "score": score,
        })
    return total_score


def get_speedrunner_score_for_users(selected_exercices: list, completion_for_users: dict) -> list:
    volume_boost = leaderboard_settings["speedrunner_volume_boost"]
    speed_boost = leaderboard_settings["speedrunner_speed_boost"]
    min_speedrunner_score = 0.006
    max_speedrunner_score = 0.6
    min_target_range = 0
    max_target_range = 10
    def normalize(score):
        return round(((score - min_speedrunner_score) / (max_speedrunner_score - min_speedrunner_score)) * (max_target_range - min_target_range) + min_target_range, 1)

    user_times = defaultdict(int)
    user_completed_tasks = defaultdict(int)
    for user_id in completion_for_users.keys():
        if user_id not in db.USER_ID_TO_EMAIL_MAPPING:
            print("unknown user id", user_id)
            continue
        for exec_uuid, tasks_completion in completion_for_users[user_id].items():
            if exec_uuid in selected_exercices:
                user_times[user_id] += get_score_for_task_completion(tasks_completion)
                user_completed_tasks[user_id] += get_completed_task_count(tasks_completion)

    user_avg_time_per_task = []
    for user_id, user_time in user_times.items():
        if user_completed_tasks[user_id] < 3:  # Skip users with less than 3 completed tasks
            continue

        speedrunner_score = (
            (user_completed_tasks[user_id] ** volume_boost) / (user_time**speed_boost)
            if user_completed_tasks[user_id] > 0 else 0
        )
        user_avg_time_per_task.append({
            "user_id": user_id,
            "email": db.USER_ID_TO_EMAIL_MAPPING[user_id],
            "user_time": user_time,
            "completed_task_count": user_completed_tasks[user_id],
            "avg_time_per_tasks": user_time / user_completed_tasks[user_id] if user_completed_tasks[user_id] > 0 else 0,
            "speedrunner_score": speedrunner_score,
            "speedrunner_score_normalized": normalize(speedrunner_score),
        })
    return user_avg_time_per_task


def get_time_on_fire_for_users(selected_exercices: list, completion_for_users: dict) -> list:
    user_completion_time = get_user_completion_time(selected_exercices, completion_for_users)
    user_on_fire_intervals = get_user_on_fire_intervals(user_completion_time)

    time_on_fire_for_users = []
    now = time.time()
    for user_id, fire_intervals in user_on_fire_intervals.items():
        intervals_duration = [int(min(now, end) - start) for start, end in fire_intervals]
        time_on_fire_for_users.append({
            "user_id": user_id,
            "email": db.USER_ID_TO_EMAIL_MAPPING[user_id],
            "time_on_fire": sum(intervals_duration),
        })

    return time_on_fire_for_users


def get_users_on_fire(selected_exercices: list, completion_for_users: dict) -> list:
    user_completion_time = get_user_completion_time(selected_exercices, completion_for_users)
    user_on_fire_intervals = get_user_on_fire_intervals(user_completion_time)
    users_on_fire = []
    now = time.time()
    for user_id in user_on_fire_intervals.keys():
        last_interval = user_on_fire_intervals[user_id][-1]
        if last_interval[0] <= now <= last_interval[1]:
            users_on_fire.append({
                "user_id": user_id,
                "email": db.USER_ID_TO_EMAIL_MAPPING[user_id],
                "time_on_fire_interval": last_interval,
            })
    return users_on_fire


def get_user_completion_time(selected_exercices: list, completion_for_users: dict) -> dict:
    user_completion_time = defaultdict(list)
    for user_id in completion_for_users.keys():
        if user_id not in db.USER_ID_TO_EMAIL_MAPPING:
            print("unknown user id", user_id)
            continue
        for exec_uuid, tasks_completion in completion_for_users[user_id].items():
            if exec_uuid in selected_exercices:
                user_completion_time[
                    user_id
                ] += get_sorted_timestamps_for_completed_tasks(tasks_completion)

    for user_id in user_completion_time.keys():
        user_completion_time[user_id].sort()

    return user_completion_time


def get_user_on_fire_intervals(user_completion_time: dict) -> list:
    fire_window = leaderboard_settings["time_one_fire_window_sec"]
    user_on_fire_intervals = defaultdict(list)
    for user_id, timestamps in user_completion_time.items():
        start = None
        end = None

        for t in timestamps:
            if end is None or t > start:
                if start is not None:
                    user_on_fire_intervals[user_id].append([start, min(t, start+fire_window)])
                start = t
            end = t + fire_window

        if start is not None:
            user_on_fire_intervals[user_id].append([start, end])
    return user_on_fire_intervals


def get_sorted_timestamps_for_completed_tasks(tasks_completion: dict) -> list:
    timestamps = []
    for inject_uuid, completed in tasks_completion.items():
        if not completed:
            continue
        timestamps.append(completed['timestamp'])
    return timestamps
