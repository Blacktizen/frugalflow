from collections import deque

def shortest(adj, start, goal):
    if start == goal:
        return [start]
    queue = deque([start])
    parent = {start: None}
    while queue:
        node = queue.popleft()
        for nb in adj.get(node, []):
            if nb in parent:
                continue
            parent[nb] = node
            if nb == goal:
                path = [goal]
                cur = node
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                return path
            queue.append(nb)
    return None
