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
    import inspect
    b = list(a)
    try:
        ps = list(inspect.signature(f).parameters.values())
        need = [p for p in ps if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    except Exception:
        need = [0]
    if len(need) == 3:
        # in-place style f(items, low, high): try inclusive high first, then exclusive
        first = None; err = None
        try:
            first = f(b, 0, len(b) - 1)
            first = b if first is None else first
            if list(first) == sorted(a): return first
        except Exception as e:
            err = e
        b2 = list(a)
        try:
            r = f(b2, 0, len(b2))
            r = b2 if r is None else r
            if list(r) == sorted(a): return r
        except Exception:
            pass
        if err is not None: raise err
        return first
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
STRUCTS = [
 {"slug": "stack", "title": "Stack", "fn": "Stack", "kind": "class",
  "sample": '''class Stack:
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)

    def pop(self):
        if self.is_empty():
            return None
        return self.items.pop()

    def peek(self):
        if self.is_empty():
            return None
        return self.items[-1]

    def is_empty(self):
        return len(self.items) == 0
''',
  "tests": '''s = Stack()
assert s.is_empty() is True, "a new Stack should be empty (is_empty() should return True)"
for v in (1, 2, 3):
    s.push(v)
assert s.is_empty() is False, "is_empty() should be False after pushes"
assert s.peek() == 3, "peek() should show the top item 3 without removing it, got %r" % (s.peek(),)
assert s.peek() == 3, "peek() must not remove the item"
got = [s.pop(), s.pop(), s.pop()]
assert got == [3, 2, 1], "pop() should give last-in first-out: expected [3, 2, 1] but got %r" % (got,)
assert s.is_empty() is True, "the Stack should be empty after popping everything"
try:
    s.pop(); s.peek()
except Exception:
    pass
s.push("a"); s.push("b"); assert s.pop() == "b"; s.push("c")
assert [s.pop(), s.pop()] == ["c", "a"], "mixed push and pop order is wrong"
'''},
 {"slug": "queue", "title": "Queue", "fn": "Queue", "kind": "class",
  "sample": '''class Queue:
    def __init__(self):
        self.items = []

    def enqueue(self, item):
        self.items.append(item)

    def dequeue(self):
        if self.is_empty():
            return None
        return self.items.pop(0)

    def peek(self):
        if self.is_empty():
            return None
        return self.items[0]

    def is_empty(self):
        return len(self.items) == 0
''',
  "tests": '''q = Queue()
assert q.is_empty() is True, "a new Queue should be empty (is_empty() should return True)"
for v in (1, 2, 3):
    q.enqueue(v)
assert q.is_empty() is False, "is_empty() should be False after enqueues"
assert q.peek() == 1, "peek() should show the front item 1 without removing it, got %r" % (q.peek(),)
assert q.peek() == 1, "peek() must not remove the item"
got = [q.dequeue(), q.dequeue(), q.dequeue()]
assert got == [1, 2, 3], "dequeue() should give first-in first-out: expected [1, 2, 3] but got %r" % (got,)
assert q.is_empty() is True, "the Queue should be empty after dequeuing everything"
try:
    q.dequeue(); q.peek()
except Exception:
    pass
q.enqueue("a"); q.enqueue("b"); assert q.dequeue() == "a"; q.enqueue("c")
assert [q.dequeue(), q.dequeue()] == ["b", "c"], "mixed enqueue and dequeue order is wrong"
for v in range(50):
    q.enqueue(v)
assert [q.dequeue() for _ in range(50)] == list(range(50)), "order wrong after many enqueues"
'''},
 {"slug": "unordered-linked-list", "title": "Linked list (unordered)", "fn": "UnorderedLinkedList", "kind": "class",
  "sample": '''class Node:
    def __init__(self, value):
        self.value = value
        self.next = None


class UnorderedLinkedList:
    def __init__(self):
        self.head = None

    def insert(self, value):
        node = Node(value)
        node.next = self.head
        self.head = node

    def search(self, value):
        current = self.head
        while current is not None:
            if current.value == value:
                return True
            current = current.next
        return False

    def delete(self, value):
        current = self.head
        previous = None
        while current is not None:
            if current.value == value:
                if previous is None:
                    self.head = current.next
                else:
                    previous.next = current.next
                return True
            previous = current
            current = current.next
        return False

    def display(self):
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        print(result)
        return result
''',
  "tests": '''_ban("deque", "sorted", "sort")
import sys, io, re
def _guard(f, *a):
    """stop a runaway loop (e.g. a circular list that never comes back to the head)"""
    st = [0]
    def tr(fr, ev, arg):
        st[0] += 1
        if st[0] > 300000:
            raise AssertionError("Your code ran far too long - a loop never stops. Check the while loop on the line named below: does current ever become None, and does every node's next end at None?")
        return tr
    old = sys.gettrace()
    sys.settrace(tr)
    try:
        return f(*a)
    finally:
        sys.settrace(old)
def _cyclic(l):
    """True if following the node links from the list ever comes back to a node already seen"""
    for v in list(vars(l).values()):
        seen = set(); n = v
        while n is not None and hasattr(n, "__dict__") and not isinstance(n, (list, dict)):
            if id(n) in seen:
                return True
            seen.add(id(n))
            nxt = [x for x in vars(n).values() if hasattr(x, "__dict__") and not isinstance(x, (list, dict))]
            n = nxt[0] if nxt else None
    return False
def _show(l):
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        r = _guard(l.display)
    finally:
        sys.stdout = old
    if r is not None:
        try:
            return [int(x) for x in r]
        except Exception:
            pass
    return [int(x) for x in re.findall(r"-?\d+", buf.getvalue())]
def _same(l, expect, what):
    got = _show(l)
    assert got == expect or got == expect[::-1] and True, "%s: display() should show %r but showed %r" % (what, expect, got)
    return got
ll = UnorderedLinkedList()
assert _show(ll) == [], "display() of an empty list should show nothing"
assert _guard(ll.search, 1) is False, "search on an empty list should be False"
assert _guard(ll.delete, 1) is False, "delete on an empty list should return False"
def _steps(f, *a):
    st = [0]
    def tr(fr, ev, arg):
        st[0] += 1
        return tr
    old = sys.gettrace(); sys.settrace(tr)
    try:
        f(*a)
    finally:
        sys.settrace(old)
    return st[0]
_seq = [10, 20, 30, 20]
for v in _seq:
    _guard(ll.insert, v)
assert _show(ll) == [20, 30, 20, 10], "insert should add at the head, so the newest item is first: display() showed %r" % (_show(ll),)
_small = _steps(ll.insert, 1)
for v in range(300):
    ll.insert(v)
_big = _steps(ll.insert, 2)
assert _big <= _small * 2 + 10, "insert should be O(1): it took %d steps on a long list but %d on a short one. Insert at the head without walking the list." % (_big, _small)
ll = UnorderedLinkedList()
for v in _seq:
    ll.insert(v)
for _v in (10, 20, 30):
    assert _guard(ll.search, _v) is True, "search(%r) should be True - an item is in the list. Check every node, including the last one." % (_v,)
assert _guard(ll.search, 99) is False, "search for a missing value should be False"
assert _guard(ll.delete, 99) is False, "delete of a target that is not in the list should return False (not found)"
assert _show(ll) == [20, 30, 20, 10], "a failed delete must leave the list unchanged: %r" % (_show(ll),)
assert _guard(ll.delete, 20) is True, "delete(20) should return True (success) when the target is found"
assert _show(ll) == [30, 20, 10], "delete should remove only the first 20: display() showed %r" % (_show(ll),)
_r = _guard(ll.delete, 10)
assert _r is True, "delete(10) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [30, 20], "deleting the last item is wrong: %r" % (_show(ll),)
_r = _guard(ll.delete, 30)
assert _r is True, "delete(30) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [20], "deleting the head is wrong: %r" % (_show(ll),)
_r = _guard(ll.delete, 20)
assert _r is True, "delete(20) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [], "deleting the only item should leave an empty list"
assert _guard(ll.delete, 20) is False and _guard(ll.search, 20) is False, "after emptying, delete and search should report not found"
_guard(ll.insert, 5)
assert _show(ll) == [5], "insert after emptying the list is wrong"
'''},
 {"slug": "ordered-linked-list", "title": "Linked list (ordered)", "fn": "OrderedLinkedList", "kind": "class",
  "sample": '''class Node:
    def __init__(self, value):
        self.value = value
        self.next = None


class OrderedLinkedList:
    def __init__(self):
        self.head = None

    def insert(self, value):
        node = Node(value)
        if self.head is None or value <= self.head.value:
            node.next = self.head
            self.head = node
            return
        current = self.head
        while current.next is not None and current.next.value < value:
            current = current.next
        node.next = current.next
        current.next = node

    def search(self, value):
        current = self.head
        while current is not None and current.value <= value:
            if current.value == value:
                return True
            current = current.next
        return False

    def delete(self, value):
        current = self.head
        previous = None
        while current is not None and current.value <= value:
            if current.value == value:
                if previous is None:
                    self.head = current.next
                else:
                    previous.next = current.next
                return True
            previous = current
            current = current.next
        return False

    def display(self):
        result = []
        current = self.head
        while current is not None:
            result.append(current.value)
            current = current.next
        print(result)
        return result
''',
  "tests": '''_ban("deque", "sorted", "sort")
import sys, io, re
def _guard(f, *a):
    """stop a runaway loop (e.g. a circular list that never comes back to the head)"""
    st = [0]
    def tr(fr, ev, arg):
        st[0] += 1
        if st[0] > 300000:
            raise AssertionError("Your code ran far too long - a loop never stops. Check the while loop on the line named below: does current ever become None, and does every node's next end at None?")
        return tr
    old = sys.gettrace()
    sys.settrace(tr)
    try:
        return f(*a)
    finally:
        sys.settrace(old)
def _cyclic(l):
    """True if following the node links from the list ever comes back to a node already seen"""
    for v in list(vars(l).values()):
        seen = set(); n = v
        while n is not None and hasattr(n, "__dict__") and not isinstance(n, (list, dict)):
            if id(n) in seen:
                return True
            seen.add(id(n))
            nxt = [x for x in vars(n).values() if hasattr(x, "__dict__") and not isinstance(x, (list, dict))]
            n = nxt[0] if nxt else None
    return False
def _show(l):
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        r = _guard(l.display)
    finally:
        sys.stdout = old
    if r is not None:
        try:
            return [int(x) for x in r]
        except Exception:
            pass
    return [int(x) for x in re.findall(r"-?\d+", buf.getvalue())]
def _same(l, expect, what):
    got = _show(l)
    assert got == expect or got == expect[::-1] and False, "%s: display() should show %r but showed %r" % (what, expect, got)
    return got
ll = OrderedLinkedList()
assert _show(ll) == [], "display() of an empty list should show nothing"
assert _guard(ll.search, 1) is False, "search on an empty list should be False"
assert _guard(ll.delete, 1) is False, "delete on an empty list should return False"
for v in (30, 10, 20, 20, 5):
    _guard(ll.insert, v)
assert _show(ll) == [5, 10, 20, 20, 30], "insert should keep the list in ascending order: display() showed %r" % (_show(ll),)
for _v in (5, 10, 20, 30):
    assert _guard(ll.search, _v) is True, "search(%r) should be True - an item is in the list. Check every node, including the last one." % (_v,)
assert _guard(ll.search, 25) is False and _guard(ll.search, 99) is False, "search for a missing value should be False"
assert _guard(ll.delete, 20) is True, "delete(20) should return True when found"
assert _show(ll) == [5, 10, 20, 30], "delete should remove only the first 20: display() showed %r" % (_show(ll),)
_r = _guard(ll.delete, 5)
assert _r is True, "delete(5) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [10, 20, 30], "deleting the head is wrong: %r" % (_show(ll),)
_r = _guard(ll.delete, 30)
assert _r is True, "delete(30) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [10, 20], "deleting the last item is wrong: %r" % (_show(ll),)
assert _guard(ll.delete, 99) is False, "delete of a target that is not in the list should return False (not found)"
assert _show(ll) == [10, 20], "a failed delete must leave the list unchanged"
_guard(ll.insert, 15)
assert _show(ll) == [10, 15, 20], "insert in the middle is wrong: %r" % (_show(ll),)
for v in (10, 15, 20):
    assert _guard(ll.delete, v) is True
assert _show(ll) == [] and _guard(ll.search, 10) is False, "deleting every item should leave an empty list"
_guard(ll.insert, 7)
assert _show(ll) == [7], "insert after emptying the list is wrong"
'''},
 {"slug": "circular-linked-list", "title": "Linked list (circular)", "fn": "CircularLinkedList", "kind": "class",
  "sample": '''class Node:
    def __init__(self, value):
        self.value = value
        self.next = None


class CircularLinkedList:
    def __init__(self):
        self.head = None

    def insert(self, value):
        node = Node(value)
        if self.head is None:
            node.next = node
            self.head = node
            return
        current = self.head
        while current.next is not self.head:
            current = current.next
        current.next = node
        node.next = self.head

    def search(self, value):
        if self.head is None:
            return False
        current = self.head
        while True:
            if current.value == value:
                return True
            current = current.next
            if current is self.head:
                return False

    def delete(self, value):
        if self.head is None:
            return False
        current = self.head
        previous = None
        while True:
            if current.value == value:
                if current.next is current:
                    self.head = None
                elif previous is None:
                    last = self.head
                    while last.next is not self.head:
                        last = last.next
                    self.head = current.next
                    last.next = self.head
                else:
                    previous.next = current.next
                return True
            previous = current
            current = current.next
            if current is self.head:
                return False

    def display(self):
        result = []
        if self.head is not None:
            current = self.head
            while True:
                result.append(current.value)
                current = current.next
                if current is self.head:
                    break
        print(result)
        return result
''',
  "tests": '''_ban("deque", "sorted", "sort")
import sys, io, re
def _guard(f, *a):
    """stop a runaway loop (e.g. a circular list that never comes back to the head)"""
    st = [0]
    def tr(fr, ev, arg):
        st[0] += 1
        if st[0] > 300000:
            raise AssertionError("Your code ran far too long - a loop never stops. For a circular list, stop when you get back to the head.")
        return tr
    old = sys.gettrace()
    sys.settrace(tr)
    try:
        return f(*a)
    finally:
        sys.settrace(old)
def _cyclic(l):
    """True if following the node links from the list ever comes back to a node already seen"""
    for v in list(vars(l).values()):
        seen = set(); n = v
        while n is not None and hasattr(n, "__dict__") and not isinstance(n, (list, dict)):
            if id(n) in seen:
                return True
            seen.add(id(n))
            nxt = [x for x in vars(n).values() if hasattr(x, "__dict__") and not isinstance(x, (list, dict))]
            n = nxt[0] if nxt else None
    return False
def _show(l):
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:
        r = _guard(l.display)
    finally:
        sys.stdout = old
    if r is not None:
        try:
            return [int(x) for x in r]
        except Exception:
            pass
    return [int(x) for x in re.findall(r"-?\d+", buf.getvalue())]
def _same(l, expect, what):
    got = _show(l)
    assert got == expect or got == expect[::-1] and True, "%s: display() should show %r but showed %r" % (what, expect, got)
    return got
ll = CircularLinkedList()
assert _show(ll) == [], "display() of an empty list should show nothing"
assert _guard(ll.search, 1) is False, "search on an empty list should be False"
assert _guard(ll.delete, 1) is False, "delete on an empty list should return False"
_seq = [10, 20, 30, 20]
for v in _seq:
    _guard(ll.insert, v)
_cur = _same(ll, _seq, "after inserts")
for _v in (10, 20, 30):
    assert _guard(ll.search, _v) is True, "search(%r) should be True - an item is in the list. Check every node, including the last one." % (_v,)
assert _guard(ll.search, 99) is False, "search for a missing value should be False"
assert _guard(ll.delete, 20) is True, "delete(20) should return True when found"
_cur = _show(ll)
assert sorted(_cur) == [10, 20, 30] and len(_cur) == 3, "delete should remove exactly one 20: display() showed %r" % (_cur,)
_r = _guard(ll.delete, 10)
assert _r is True, "delete(10) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert sorted(_show(ll)) == [20, 30], "deleting the head or an end is wrong: %r" % (_show(ll),)
assert _guard(ll.delete, 99) is False, "delete of a target that is not in the list should return False (not found)"
_r = _guard(ll.delete, 30)
assert _r is True, "delete(30) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [20], "delete is wrong: %r" % (_show(ll),)
_r = _guard(ll.delete, 20)
assert _r is True, "delete(20) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert _show(ll) == [], "deleting the only item should leave an empty list"
assert _guard(ll.search, 20) is False, "search after emptying should be False"
_guard(ll.insert, 5)
assert _show(ll) == [5], "insert after emptying the list is wrong"
_c = CircularLinkedList()
for v in (1, 2, 3):
    _guard(_c.insert, v)
assert _cyclic(_c), "this is not circular: the last node's link should point back to the head"
for _v in (1, 2, 3):
    assert _guard(_c.search, _v) is True, "search(%r) should be True - an item is in the list. Check every node, including the last one before you get back to the head." % (_v,)
assert _guard(_c.search, 9) is False, "search for a missing value should be False"
assert sorted(_show(_c)) == [1, 2, 3] and len(_show(_c)) == 3, "display() should show each item once, not go round again: %r" % (_show(_c),)
_r = _guard(_c.delete, 2)
assert _r is True, "delete(2) should return True when it removes the item, but it returned %r (return True for success, False for not found)" % (_r,)
assert sorted(_show(_c)) == [1, 3], "delete in a circular list is wrong: %r" % (_show(_c),)
_c.insert(4)
assert sorted(_show(_c)) == [1, 3, 4], "insert after a delete is wrong"
'''},
 {"slug": "hash-table", "title": "Hash table (insert and search)", "fn": "HashTable", "kind": "class",
  "sample": '''class HashTable:
    def __init__(self, size=10):
        self.size = size
        self.slots = [[] for _ in range(size)]

    def _hash(self, key):
        if isinstance(key, int):
            return key % self.size
        total = 0
        for ch in str(key):
            total = total + ord(ch)
        return total % self.size

    def insert(self, key, value):
        bucket = self.slots[self._hash(key)]
        for pair in bucket:
            if pair[0] == key:
                pair[1] = value
                return
        bucket.append([key, value])

    def search(self, key):
        bucket = self.slots[self._hash(key)]
        for pair in bucket:
            if pair[0] == key:
                return pair[1]
        return None
''',
  "tests": '''_ban("dict", "defaultdict", "OrderedDict")
h = HashTable()
assert h.search(5) is None, "search for a missing key should return None"
pairs = [(5, "a"), (15, "b"), (25, "c"), (7, "d"), (17, "e"), ("apple", 1), ("pear", 2)]
for k, v in pairs:
    h.insert(k, v)
for k, v in pairs:
    got = h.search(k)
    assert got == v, "search(%r) should give %r but gave %r (check collisions are handled)" % (k, v, got)
assert h.search(35) is None and h.search("plum") is None, "search for a missing key should return None"
h.insert(15, "z")
assert h.search(15) == "z" and h.search(5) == "a" and h.search(25) == "c", "inserting an existing key should update its value only"
'''},
 {"slug": "binary-search-tree", "title": "Binary search tree", "fn": "BST", "kind": "class", "limit_min": 8,
  "sample": '''class Node:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None


class BST:
    def __init__(self):
        self.root = None

    def insert(self, value):
        self.root = self._insert(self.root, value)

    def _insert(self, node, value):
        if node is None:
            return Node(value)
        if value < node.value:
            node.left = self._insert(node.left, value)
        elif value > node.value:
            node.right = self._insert(node.right, value)
        return node

    def search(self, value):
        node = self.root
        while node is not None:
            if value == node.value:
                return True
            node = node.left if value < node.value else node.right
        return False

    def inorder(self, node="start"):
        if node == "start":
            node = self.root
        if node is None:
            return []
        return self.inorder(node.left) + [node.value] + self.inorder(node.right)

    def preorder(self, node="start"):
        if node == "start":
            node = self.root
        if node is None:
            return []
        return [node.value] + self.preorder(node.left) + self.preorder(node.right)

    def postorder(self, node="start"):
        if node == "start":
            node = self.root
        if node is None:
            return []
        return self.postorder(node.left) + self.postorder(node.right) + [node.value]

    def reverse(self, node="start"):
        # reverse in-order: right, root, left (largest to smallest)
        if node == "start":
            node = self.root
        if node is None:
            return []
        return self.reverse(node.right) + [node.value] + self.reverse(node.left)

    def maximum(self):
        node = self.root
        while node is not None and node.right is not None:
            node = node.right
        return node.value if node else None

    def minimum(self):
        node = self.root
        while node is not None and node.left is not None:
            node = node.left
        return node.value if node else None
''',
  "tests": '''_ban("sorted", "sort", "max", "min")
t = BST()
assert t.inorder() == [] and t.preorder() == [] and t.postorder() == [] and t.reverse() == [], "traversals of an empty tree should give []"
assert t.search(1) is False, "search on an empty tree should be False"
try:
    t.maximum(); t.minimum()
except Exception:
    pass
for v in (50, 30, 70, 20, 40, 60, 80, 35, 45):
    t.insert(v)
assert t.inorder() == [20, 30, 35, 40, 45, 50, 60, 70, 80], "inorder should be left, root, right: got %r" % (t.inorder(),)
assert t.preorder() == [50, 30, 20, 40, 35, 45, 70, 60, 80], "preorder should be root, left, right: got %r" % (t.preorder(),)
assert t.postorder() == [20, 35, 45, 40, 30, 60, 80, 70, 50], "postorder should be left, right, root: got %r" % (t.postorder(),)
assert t.reverse() == [80, 70, 60, 50, 45, 40, 35, 30, 20], "reverse should list the values from largest to smallest: got %r" % (t.reverse(),)
assert t.maximum() == 80 and t.minimum() == 20, "maximum should be 80 and minimum 20, got %r and %r" % (t.maximum(), t.minimum())
for v in (45, 20, 80, 60):
    assert t.search(v) is True, "search(%r) should be True" % (v,)
for v in (10, 55, 99):
    assert t.search(v) is False, "search(%r) should be False" % (v,)
random.seed(5)
vals = random.sample(range(1000), 60)
t2 = BST()
for v in vals:
    t2.insert(v)
assert t2.inorder() == sorted(vals), "inorder on a larger random tree is wrong"
assert t2.maximum() == max(vals) and t2.minimum() == min(vals), "maximum/minimum wrong on a larger tree"
assert all(t2.search(v) for v in vals), "search missed an inserted value"
'''},
]
for _a in ALGOS:
    _a.setdefault("kind", "func"); _a.setdefault("group", "Algorithms")
for _a in STRUCTS:
    _a.setdefault("group", "Data structures")
ALGOS.extend(STRUCTS)
for _a in ALGOS:
    _a["limit_ms"] = _a.get("limit_min", 5) * 60000
    _a["limit_min"] = _a.get("limit_min", 5)

BY_SLUG = {a["slug"]: a for a in ALGOS}

def band(ms, slug=None):
    """green within the limit, orange within one minute over, red beyond."""
    limit = BY_SLUG[slug]["limit_ms"] if slug in BY_SLUG else TARGET_MS
    if ms <= limit: return "green"
    if ms < limit + 60000: return "orange"
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
    nclass = sum(isinstance(n, _ast.ClassDef) for n in _ast.walk(tree))
    if slug == "hash-table":
        if any(isinstance(n, _ast.Dict) for n in _ast.walk(tree)):
            notes.append("uses a Python dict instead of an array and a hash function")
    elif slug.endswith("-linked-list"):
        if nclass < 2:
            notes.append("no separate node class holding a pointer to the next node found")
        if slug == "circular-linked-list":
            heads = [n for n in _ast.walk(tree) if isinstance(n, _ast.Compare) and any(
                (isinstance(x, _ast.Attribute) and x.attr in ("head", "start", "first")) or (isinstance(x, _ast.Name) and x.id in ("head", "start", "first")) for x in [n.left] + n.comparators)]
            if not heads:
                notes.append("no check for coming back round to the head found, which is what makes the list circular")
    elif slug == "binary-search-tree":
        if nclass < 2:
            notes.append("no separate node class with left and right links found")
    return notes
