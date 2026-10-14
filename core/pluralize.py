def pluralize(n: float, one: str, few: str, many: str) -> str:
    if n != int(n):
        return few
    n_abs = abs(int(n))
    if 11 <= n_abs % 100 <= 14:
        return many
    last_digit = n_abs % 10
    if last_digit == 1:
        return one
    if 2 <= last_digit <= 4:
        return few
    return many