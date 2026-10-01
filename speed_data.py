"""Speed-drill algorithms: sample code shown to students and the hidden tests.
Tests run in the browser (Pyodide) after the student's code; _SRC holds the raw code."""

TARGET_MS = 5 * 60 * 1000
ORANGE_MS = 6 * 60 * 1000

PRE = '''import ast, random
def _names(src):
    try:
        t = ast.parse(src)
    except SyntaxError:
        return set()
    s = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Name): s.add(n.id)
        if isinstance(n, ast.Attribute): s.add(n.attr)
    return s
def _ban(*bad):
    hit = sorted(_names(_SRC) & set(bad))
    assert not hit, "Do not use built-in shortcuts: " + ", ".join(hit)
class _Spy(list):
    reads = 0
    writes = 0
    def __getitem__(self, i):
        if isinstance(i, int): self.reads += 1
        return list.__getitem__(self, i)
    def __setitem__(self, i, v):
        self.writes += 1
        list.__setitem__(self, i, v)
def _res(f, a):
    b = list(a)
    r = f(b)
    return b if r is None else r
'''

SORT_TESTS = '''
_ban("sorted", "sort", "heapify", "nlargest", "nsmallest")
for a in ([], [1], [2, 1], [5, 3, 8, 1, 9, 2], [4, 4, 1, 4], [-3, 7, 0, -3, 2], [1, 2, 3, 4, 5], [9, 8, 7, 6, 5, 4]):
    got = _res(FN, a)
    assert list(got) == sorted(a), "%s(%r) should give %r but gave %r" % (NAME, a, sorted(a), got)
random.seed(7)
for _ in range(25):
    a = [random.randint(-20, 20) for _ in range(random.randint(0, 14))]
    got = _res(FN, a)
    assert list(got) == sorted(a), "%s(%r) should give %r but gave %r" % (NAME, a, sorted(a), got)
'''

_CX = '''
class _C:
    n = 0
    def __init__(self, v): self.v = v
    def __lt__(self, o): _C.n += 1; return self.v < o.v
    def __le__(self, o): _C.n += 1; return self.v <= o.v
    def __gt__(self, o): _C.n += 1; return self.v > o.v
    def __ge__(self, o): _C.n += 1; return self.v >= o.v
    def __eq__(self, o): _C.n += 1; return self.v == o.v
    def __ne__(self, o): _C.n += 1; return self.v != o.v
    __hash__ = None
random.seed(11)
_vals = random.sample(range(10000), 800)
_got = _res(FN, [_C(v) for v in _vals])
assert [x.v for x in _got] == sorted(_vals), "%s gave a wrong order on a longer list" % NAME
assert _C.n <= 100000, "Performance check on a random 800-item list: %s used %d comparisons, far more than a typical n log n sort. Check you split or partition instead of comparing everything with everything." % (NAME, _C.n)
'''
EXTRA = {"bubble_sort": "", "insertion_sort": "", "merge_sort": _CX, "quick_sort": _CX}

def _sort_tests(name):
    return "FN = %s\nNAME = %r\n" % (name, name) + SORT_TESTS + EXTRA[name]

ALGOS = [
 {"slug": "linear-search", "title": "Linear search", "fn": "linear_search",
  "sample": '''def linear_search(items, target):
    for i in range(len(items)):
        if items[i] == target:
            return i
    return -1
''',
  "tests": '''_ban("index", "find", "count")
_cases = [([], 1, -1), ([5], 5, 0), ([5], 6, -1), ([3, 8, 1, 9], 9, 3), ([3, 8, 1, 9], 3, 0),
          ([3, 8, 1, 9], 4, -1), ([2, 7, 2, 7], 7, 1), (["a", "b", "c"], "c", 2)]
for a, t, exp in _cases:
    got = linear_search(list(a), t)
    assert got == exp, "linear_search(%r, %r) should give %r but gave %r" % (a, t, exp, got)
'''},
 {"slug": "binary-search", "title": "Binary search", "fn": "binary_search",
  "sample": '''def binary_search(items, target):
    low = 0
    high = len(items) - 1
    while low <= high:
        mid = (low + high) // 2
        if items[mid] == target:
            return mid
        elif items[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
''',
  "tests": '''_ban("index", "bisect", "bisect_left", "bisect_right", "find", "count")
assert binary_search([], 3) == -1, "binary_search([], 3) should give -1"
_big = _Spy(range(0, 4000, 2))
assert binary_search(_big, 2000) == 1000, "binary_search should find 2000 at index 1000 in a sorted list"
assert _big.reads <= 40, "That looks like a linear scan (%d item reads on 2000 items). Binary search should halve the range each step." % _big.reads
for a in ([4], [1, 3], [1, 3, 5, 7, 9], [2, 4, 6, 8, 10, 12], list(range(0, 40, 3))):
    for i, v in enumerate(a):
        got = binary_search(list(a), v)
        assert got == i, "binary_search(%r, %r) should give %r but gave %r" % (a, v, i, got)
    for miss in (a[0] - 1, a[-1] + 1, a[0] + 1 if (a[0] + 1) not in a else a[-1] + 2):
        got = binary_search(list(a), miss)
        assert got == -1, "binary_search(%r, %r) should give -1 but gave %r" % (a, miss, got)
'''},
 {"slug": "bubble-sort", "title": "Bubble sort", "fn": "bubble_sort",
  "sample": '''def bubble_sort(items):
    n = len(items)
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            if items[j] > items[j + 1]:
                items[j], items[j + 1] = items[j + 1], items[j]
                swapped = True
        if not swapped:
            break
    return items
''',
  "tests": _sort_tests("bubble_sort")},
 {"slug": "insertion-sort", "title": "Insertion sort", "fn": "insertion_sort",
  "sample": '''def insertion_sort(items):
    for i in range(1, len(items)):
        key = items[i]
        j = i - 1
        while j >= 0 and items[j] > key:
            items[j + 1] = items[j]
            j = j - 1
        items[j + 1] = key
    return items
''',
  "tests": _sort_tests("insertion_sort")},
 {"slug": "merge-sort", "title": "Merge sort", "fn": "merge_sort",
  "sample": '''def merge_sort(items):
    if len(items) <= 1:
        return items
    mid = len(items) // 2
    left = merge_sort(items[:mid])
    right = merge_sort(items[mid:])
    result = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i = i + 1
        else:
            result.append(right[j])
            j = j + 1
    result = result + left[i:] + right[j:]
    return result
''',
  "tests": _sort_tests("merge_sort")},
 {"slug": "quicksort", "title": "Quicksort", "fn": "quick_sort",
  "sample": '''def quick_sort(items):
    if len(items) <= 1:
        return items
    pivot = items[len(items) // 2]
    left = [x for x in items if x < pivot]
    middle = [x for x in items if x == pivot]
    right = [x for x in items if x > pivot]
    return quick_sort(left) + middle + quick_sort(right)
''',
  "tests": _sort_tests("quick_sort")},
]
BY_SLUG = {a["slug"]: a for a in ALGOS}

def band(ms):
    if ms <= TARGET_MS: return "green"
    if ms < ORANGE_MS: return "orange"
    return "red"


# ---- soft logic check (AST only, safe to run on untrusted text) ----
import ast as _ast

def _subs(node):
    return [n for n in _ast.walk(node) if isinstance(n, _ast.Subscript)]

def _base(n):
    return n.value.id if isinstance(n.value, _ast.Name) else None

def _idx(n):
    return n.slice

def _adjacent(a, b):
    """True when subscripts a and b index the same list at X and X+-1."""
    if _base(a) is None or _base(a) != _base(b):
        return False
    def off(e):
        if isinstance(e, _ast.BinOp) and isinstance(e.op, (_ast.Add, _ast.Sub)) and isinstance(e.right, _ast.Constant) and e.right.value == 1:
            return _ast.dump(e.left), (1 if isinstance(e.op, _ast.Add) else -1)
        return _ast.dump(e), 0
    (ka, oa), (kb, ob) = off(_idx(a)), off(_idx(b))
    return ka == kb and abs(oa - ob) == 1

def logic_notes(slug, code):
    """Notes for teacher review when code passes the tests but does not look like the named algorithm.
    Heuristic: it never rejects a correct answer, it only holds the time off the leaderboard."""
    try:
        tree = _ast.parse(code)
    except SyntaxError:
        return []
    fns = [n for n in _ast.walk(tree) if isinstance(n, _ast.FunctionDef)]
    recursive = any(isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name) and c.func.id == f.name
                    for f in fns for c in _ast.walk(f))
    cmps = [c for c in _ast.walk(tree) if isinstance(c, _ast.Compare)]
    adj = any(len(c.comparators) == 1 and isinstance(c.left, _ast.Subscript) and isinstance(c.comparators[0], _ast.Subscript)
              and _adjacent(c.left, c.comparators[0]) for c in cmps)
    two_base = any(len(c.comparators) == 1 and isinstance(c.left, _ast.Subscript) and isinstance(c.comparators[0], _ast.Subscript)
                   and _base(c.left) and _base(c.comparators[0]) and _base(c.left) != _base(c.comparators[0]) for c in cmps)
    loops = [n for n in _ast.walk(tree) if isinstance(n, (_ast.For, _ast.While))]
    def nested(kind=None):
        for o in loops:
            for i in _ast.walk(o):
                if i is not o and isinstance(i, (_ast.For, _ast.While)) and (kind is None or isinstance(i, kind)):
                    return True
        return False
    notes = []
    if slug == "bubble-sort":
        if recursive or not nested() or not adj:
            notes.append("no nested loops comparing neighbouring items found, which is what bubble sort does")
    elif slug == "insertion-sort":
        if recursive or not nested():
            notes.append("no loop that scans back through the sorted part found, which is what insertion sort does")
        elif adj and not any(isinstance(n, _ast.While) for n in _ast.walk(tree)) and not any(
                isinstance(n, _ast.Attribute) and n.attr == "insert" for n in _ast.walk(tree)):
            notes.append("looks like swapping neighbours in passes (bubble sort) rather than insertion sort")
    elif slug == "merge-sort":
        if not recursive and not two_base:
            notes.append("no recursive halving or merge of two sorted lists found")
        elif not two_base:
            notes.append("no step comparing the front of two sorted halves found, which is the merge step")
    elif slug == "quicksort":
        if not recursive:
            notes.append("no recursion on a pivot partition found (an explicit-stack version needs review)")
        elif two_base and not any(isinstance(n, _ast.Name) and "pivot" in n.id.lower() for n in _ast.walk(tree)):
            notes.append("looks like merging two sorted lists (merge sort) rather than partitioning on a pivot")
    return notes
