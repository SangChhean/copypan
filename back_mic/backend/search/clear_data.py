from search.clear_bib import clear_bib


def _get_total(total_field):
    """ES 6 为数字，ES 7+ 为 {"value": N}"""
    if isinstance(total_field, dict):
        return total_field.get("value", 0)
    return int(total_field) if total_field is not None else 0


def clear_data(res, field):
    arr = []
    hits = res.get("hits", {}).get("hits", [])
    total_field = res.get("hits", {}).get("total", 0)
    total = _get_total(total_field)
    for hit in hits:
        try:
            arr.append(clear_bib(hit, field))
        except (KeyError, TypeError, IndexError):
            # 缺少 highlight/field 等时跳过该条，不中断整体
            continue
    return {"total": total, "msg": arr}
