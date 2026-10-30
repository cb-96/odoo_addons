def compare_cohorts(previous, current):
    previous, current = set(previous), set(current)
    returning = previous & current
    return {
        'previous': len(previous), 'current': len(current),
        'returning': len(returning), 'new': len(current - previous),
        'not_returned': len(previous - current),
        'retention_percent': round(100 * len(returning) / len(previous), 2) if previous else None,
    }
