def sorted_entries(entries):
    # TODO: break ties on the same date by description
    return sorted(entries, key=lambda e: e[0])
