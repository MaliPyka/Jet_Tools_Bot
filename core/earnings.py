def calculate_touches(old: int, new: int, corrections: int, far: int, battery: int) -> float:
    raw = old * 1 + new * 1.25 + corrections * 1 + far * 5 + battery * 1.5
    return raw


DAY_DISCOUNT = 10


def calculate_earnings(touches: float, worker_type: str = "night") -> int:
    touches = round(touches)

    if touches <= 60:
        amount = 70
    else:
        extra = touches - 60
        floor_extra = (extra // 20) * 20
        if extra - floor_extra >= 15:
            floor_extra += 20
        amount = 70 + (floor_extra // 20) * 10

    return amount - DAY_DISCOUNT if worker_type == "day" else amount


def calculate_charger_earnings(swaps: int) -> int:
    """1 замена = 1 лари; от 100 замен все замены считаются с коэффициентом 1.2."""
    if swaps >= 100:
        return (swaps * 6 + 2) // 5  # swaps * 1.2, округление до целого
    return swaps
