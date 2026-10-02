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
 {"slug": "stack", "title": "Stack (Python built-in functions)", "fn": "Stack", "kind": "class",
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
 {"slug": "stack-array", "title": "Stack (with top)", "fn": "ArrayStack", "kind": "class",
  "sample": '''class ArrayStack:
    def __init__(self, size=5):
        self.size = size
        self.items = [None] * size
        self.top = -1

    def push(self, item):
        if self.is_full():
            return False
        self.top = self.top + 1
        self.items[self.top] = item
        return True

    def pop(self):
        if self.is_empty():
            return None
        item = self.items[self.top]
        self.top = self.top - 1
        return item

    def peek(self):
        if self.is_empty():
            return None
        return self.items[self.top]

    def is_empty(self):
        return self.top == -1

    def is_full(self):
        return self.top == self.size - 1
''',
  "tests": '''_ban("append", "insert", "remove", "extend")
s = ArrayStack(3)
assert s.top == -1, "a new stack has top = -1 (nothing stored yet), got %r" % (s.top,)
assert s.is_empty() is True and s.is_full() is False, "a new stack is empty and not full"
assert s.pop() is None and s.peek() is None, "pop() and peek() on an empty stack should return None"
assert s.push("a") is True and s.top == 0, "push should return True and move top to 0, got top = %r" % (s.top,)
assert s.push("b") is True and s.push("c") is True, "push should return True while there is space"
assert s.top == 2 and s.is_full() is True, "three pushes fill a size-3 stack with top = 2"
assert s.push("d") is False, "push on a full stack should return False"
assert s.top == 2, "a failed push must not move top"
assert len(s.items) == 3, "the array must stay a fixed size of 3, but it has %d slots" % len(s.items)
assert s.peek() == "c" and s.top == 2, "peek() should show the top item 'c' without moving top"
assert s.pop() == "c" and s.top == 1, "pop() should return 'c' and move top down to 1, got top = %r" % (s.top,)
assert s.is_full() is False, "the stack is no longer full after a pop"
assert [s.pop(), s.pop()] == ["b", "a"], "pop() should give last-in first-out"
assert s.top == -1 and s.is_empty() is True, "after popping everything top is -1 again"
assert s.pop() is None, "pop() on an empty stack should return None"
s.push(1); s.push(2); assert s.pop() == 2; s.push(3)
assert [s.pop(), s.pop()] == [3, 1], "mixed push and pop order is wrong"
big = ArrayStack()
for v in range(5):
    assert big.push(v) is True, "the default size is 5, so push(%d) should work" % v
assert big.push(5) is False, "the default size is 5, so the 6th push should return False"
'''},
 {"slug": "queue", "title": "Queue (Python built-in functions)", "fn": "Queue", "kind": "class",
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
 {"slug": "queue-array", "title": "Queue (with front and rear)", "fn": "ArrayQueue", "kind": "class",
  "sample": '''class ArrayQueue:
    def __init__(self, size=5):
        self.size = size
        self.items = [None] * size
        self.front = 0
        self.rear = -1
        self.count = 0

    def enqueue(self, item):
        if self.is_full():
            return False
        self.rear = (self.rear + 1) % self.size
        self.items[self.rear] = item
        self.count = self.count + 1
        return True

    def dequeue(self):
        if self.is_empty():
            return None
        item = self.items[self.front]
        self.front = (self.front + 1) % self.size
        self.count = self.count - 1
        return item

    def peek(self):
        if self.is_empty():
            return None
        return self.items[self.front]

    def is_empty(self):
        return self.count == 0

    def is_full(self):
        return self.count == self.size
''',
  "tests": '''_ban("append", "insert", "remove", "extend")
q = ArrayQueue(3)
assert q.front == 0 and q.rear == -1, "a new queue has front = 0 and rear = -1, got front = %r, rear = %r" % (q.front, q.rear)
assert q.is_empty() is True and q.is_full() is False, "a new queue is empty and not full"
assert q.dequeue() is None and q.peek() is None, "dequeue() and peek() on an empty queue should return None"
assert q.enqueue("a") is True and q.rear == 0, "enqueue should return True and move rear to 0, got rear = %r" % (q.rear,)
assert q.enqueue("b") is True and q.enqueue("c") is True, "enqueue should return True while there is space"
assert q.rear == 2 and q.front == 0 and q.is_full() is True, "three enqueues fill a size-3 queue: rear 2, front 0"
assert q.enqueue("d") is False, "enqueue on a full queue should return False"
assert q.rear == 2, "a failed enqueue must not move rear"
assert len(q.items) == 3, "the array must stay a fixed size of 3, but it has %d slots" % len(q.items)
assert q.peek() == "a" and q.front == 0, "peek() should show the front item 'a' without moving front"
assert q.dequeue() == "a" and q.front == 1, "dequeue() should return 'a' and move front to 1, got front = %r" % (q.front,)
assert q.is_full() is False, "the queue is no longer full after a dequeue"
assert q.enqueue("d") is True, "after a dequeue there is space again, so enqueue('d') should work"
assert q.rear == 0, "rear should wrap around to index 0 (use % size), got rear = %r" % (q.rear,)
assert q.items[0] == "d", "the wrapped item should be stored at index 0, but items is %r" % (q.items,)
assert q.is_full() is True and q.enqueue("e") is False, "the queue is full again, enqueue should return False"
assert [q.dequeue(), q.dequeue(), q.dequeue()] == ["b", "c", "d"], "dequeue() should give first-in first-out across the wraparound"
assert q.front == 1 and q.rear == 0, "front should have wrapped to 1 (after 3 more dequeues) and rear stays 0, got front = %r, rear = %r" % (q.front, q.rear)
assert q.is_empty() is True and q.dequeue() is None, "the queue is empty again"
for round_ in range(4):
    for v in range(3):
        assert q.enqueue((round_, v)) is True, "enqueue should work on a queue that has space (round %d)" % round_
    assert q.enqueue("x") is False, "a full queue should reject enqueue"
    assert [q.dequeue() for _ in range(3)] == [(round_, 0), (round_, 1), (round_, 2)], "order wrong after wrapping (round %d)" % round_
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
 {"slug": "binary-search-tree", "title": "Binary search tree (linked version)", "fn": "BST", "kind": "class", "limit_min": 8,
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
 {"slug": "bst-array", "title": "Binary search tree (array version)", "fn": "ArrayBST", "kind": "class", "limit_min": 8,
  "sample": '''class ArrayBST:
    # root is index 0; for the node at index i:
    # left child is at 2*i + 1, right child is at 2*i + 2
    def __init__(self, size=15):
        self.size = size
        self.tree = [None] * size

    def insert(self, value):
        i = 0
        while i < self.size:
            if self.tree[i] is None:
                self.tree[i] = value
                return True
            if value == self.tree[i]:
                return False
            if value < self.tree[i]:
                i = 2 * i + 1
            else:
                i = 2 * i + 2
        return False

    def search(self, value):
        i = 0
        while i < self.size and self.tree[i] is not None:
            if value == self.tree[i]:
                return True
            if value < self.tree[i]:
                i = 2 * i + 1
            else:
                i = 2 * i + 2
        return False

    def inorder(self, i=0):
        if i >= self.size or self.tree[i] is None:
            return []
        return self.inorder(2 * i + 1) + [self.tree[i]] + self.inorder(2 * i + 2)

    def preorder(self, i=0):
        if i >= self.size or self.tree[i] is None:
            return []
        return [self.tree[i]] + self.preorder(2 * i + 1) + self.preorder(2 * i + 2)

    def postorder(self, i=0):
        if i >= self.size or self.tree[i] is None:
            return []
        return self.postorder(2 * i + 1) + self.postorder(2 * i + 2) + [self.tree[i]]

    def maximum(self):
        if self.tree[0] is None:
            return None
        i = 0
        while 2 * i + 2 < self.size and self.tree[2 * i + 2] is not None:
            i = 2 * i + 2
        return self.tree[i]

    def minimum(self):
        if self.tree[0] is None:
            return None
        i = 0
        while 2 * i + 1 < self.size and self.tree[2 * i + 1] is not None:
            i = 2 * i + 1
        return self.tree[i]
''',
  "tests": '''_ban("sorted", "sort", "max", "min", "Node", "append")
t = ArrayBST(7)
assert len(t.tree) == 7 and all(x is None for x in t.tree), "a new tree is a list of 7 empty (None) slots, got %r" % (t.tree,)
assert t.inorder() == [] and t.preorder() == [] and t.postorder() == [], "traversals of an empty tree should give []"
assert t.search(1) is False and t.maximum() is None and t.minimum() is None, "an empty tree: search is False, maximum and minimum are None"
assert t.insert(50) is True and t.tree[0] == 50, "the first value goes in the root, index 0"
assert t.insert(30) is True and t.tree[1] == 30, "30 < 50 goes to the left child, index 2*0+1 = 1, but tree is %r" % (t.tree,)
assert t.insert(70) is True and t.tree[2] == 70, "70 > 50 goes to the right child, index 2*0+2 = 2, but tree is %r" % (t.tree,)
assert t.insert(20) is True and t.tree[3] == 20, "20 goes to the left child of index 1, which is 2*1+1 = 3, but tree is %r" % (t.tree,)
assert t.insert(40) is True and t.tree[4] == 40, "40 goes to the right child of index 1, which is 2*1+2 = 4, but tree is %r" % (t.tree,)
assert t.insert(60) is True and t.tree[5] == 60, "60 goes to the left child of index 2, which is 2*2+1 = 5, but tree is %r" % (t.tree,)
assert t.insert(80) is True and t.tree[6] == 80, "80 goes to the right child of index 2, which is 2*2+2 = 6, but tree is %r" % (t.tree,)
assert t.tree == [50, 30, 70, 20, 40, 60, 80], "the full tree should be [50, 30, 70, 20, 40, 60, 80] but is %r" % (t.tree,)
assert t.insert(50) is False and t.insert(40) is False, "a duplicate value should return False"
assert t.insert(10) is False, "10 would need index 7, past the end of a size-7 array, so insert should return False"
assert t.tree == [50, 30, 70, 20, 40, 60, 80] and len(t.tree) == 7, "a failed insert must not change the array or its size"
t = ArrayBST(7)
for v in (1, 2, 3):
    assert t.insert(v) is True, "insert(%r) should work" % (v,)
assert t.tree == [1, None, 2, None, None, None, 3], "inserting 1, 2, 3 in order gives a chain to the right: indexes 0, 2, 6, but tree is %r" % (t.tree,)
assert t.insert(4) is False, "4 would need index 14, past the end of a size-7 array, so insert should return False"
t = ArrayBST(31)
for v in (50, 30, 70, 20, 40, 60, 80, 35, 45):
    t.insert(v)
assert t.tree[:11] == [50, 30, 70, 20, 40, 60, 80, None, None, 35, 45], "35 and 45 are the children of 40 (index 4): indexes 9 and 10, but tree is %r" % (t.tree,)
assert t.insert(40) is False and t.insert(35) is False and t.insert(45) is False, "a duplicate value should return False"
assert t.tree[:11] == [50, 30, 70, 20, 40, 60, 80, None, None, 35, 45] and t.tree[11:] == [None] * 20, "a duplicate must not be stored again, but tree is %r" % (t.tree,)
assert t.inorder() == [20, 30, 35, 40, 45, 50, 60, 70, 80], "inorder should be left, root, right: got %r" % (t.inorder(),)
assert t.preorder() == [50, 30, 20, 40, 35, 45, 70, 60, 80], "preorder should be root, left, right: got %r" % (t.preorder(),)
assert t.postorder() == [20, 35, 45, 40, 30, 60, 80, 70, 50], "postorder should be left, right, root: got %r" % (t.postorder(),)
assert t.maximum() == 80 and t.minimum() == 20, "maximum should be 80 and minimum 20, got %r and %r" % (t.maximum(), t.minimum())
for v in (45, 20, 80, 60):
    assert t.search(v) is True, "search(%r) should be True" % (v,)
for v in (10, 55, 99):
    assert t.search(v) is False, "search(%r) should be False" % (v,)
random.seed(5)
vals = random.sample(range(1000), 40)
t2 = ArrayBST(8191)
for v in vals:
    assert t2.insert(v) is True, "insert(%r) should work while there is space" % (v,)
assert t2.inorder() == sorted(vals), "inorder on a larger random tree is wrong"
assert t2.maximum() == max(vals) and t2.minimum() == min(vals), "maximum/minimum wrong on a larger tree"
assert all(t2.search(v) for v in vals), "search missed an inserted value"
'''},
]

OTHERS = [
 {"slug": "relational-database", "title": "Relational database (SQL)", "fn": "SQL script", "kind": "sql", "group": "Others",
  "sample": '''CREATE TABLE Student (
    StudentID INTEGER PRIMARY KEY,
    Name TEXT
);

CREATE TABLE Enrolment (
    EnrolID INTEGER PRIMARY KEY,
    StudentID INTEGER,
    Course TEXT,
    FOREIGN KEY (StudentID) REFERENCES Student(StudentID)
);

INSERT INTO Student VALUES (1, 'Ann');
INSERT INTO Student VALUES (2, 'Ben');
INSERT INTO Enrolment VALUES (1, 1, 'Computing');
INSERT INTO Enrolment VALUES (2, 2, 'Maths');

SELECT Student.Name, Enrolment.Course
FROM Student, Enrolment
WHERE Student.StudentID = Enrolment.StudentID;

UPDATE Student SET Name = 'Anna' WHERE StudentID = 1;

DELETE FROM Enrolment WHERE EnrolID = 2;
''',
  "tests": '''import sqlite3
db = sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys = ON")
stmts, buf = [], ""
for line in _SRC.splitlines(True):
    buf += line
    if sqlite3.complete_statement(buf):
        stmts.append(buf.strip()); buf = ""
assert not buf.strip(), "The last statement is not finished. Check it ends with a semicolon: " + buf.strip()[:60]
assert stmts, "Type the SQL script into the editor first"
sel = []
kinds = []
for n, st in enumerate(stmts, 1):
    word = st.split(None, 1)[0].upper()
    kinds.append(word + (" TABLE" if word == "CREATE" else ""))
    try:
        cur = db.execute(st)
    except sqlite3.Error as e:
        raise AssertionError("SQL error in statement %d (%s ...): %s" % (n, st[:45].replace("\\n", " "), e)) from None
    if word == "SELECT":
        sel.append((st, cur.fetchall()))
db.commit()
assert kinds.count("CREATE TABLE") == 2, "Create exactly 2 tables, you have %d CREATE TABLE statements" % kinds.count("CREATE TABLE")
tabs = sorted(r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"))
assert tabs == ["Enrolment", "Student"], "The tables should be called Student and Enrolment, but you have %r" % (tabs,)
cols = lambda t: [(r[1], r[5]) for r in db.execute("PRAGMA table_info(%s)" % t)]
assert cols("Student") == [("StudentID", 1), ("Name", 0)], "Student needs columns StudentID (the PRIMARY KEY) then Name, but has %r" % (cols("Student"),)
assert [c[0] for c in cols("Enrolment")] == ["EnrolID", "StudentID", "Course"] and cols("Enrolment")[0][1] == 1, "Enrolment needs columns EnrolID (the PRIMARY KEY), StudentID, Course, but has %r" % (cols("Enrolment"),)
fk = [(r[2], r[3], r[4]) for r in db.execute("PRAGMA foreign_key_list(Enrolment)")]
assert fk == [("Student", "StudentID", "StudentID")], "Enrolment.StudentID should be a FOREIGN KEY REFERENCES Student(StudentID), found %r" % (fk,)
for k in ("INSERT", "SELECT", "UPDATE", "DELETE"):
    assert k in kinds, "No %s statement found" % k
assert kinds.index("SELECT") > max(i for i, k in enumerate(kinds) if k == "INSERT"), "Run the SELECT after the INSERT statements"
assert len(sel) == 1, "Use exactly one SELECT statement"
q, rows = sel[0]
ql = q.lower()
assert "student" in ql and "enrolment" in ql, "The SELECT must use both tables (Student and Enrolment)"
assert "student.studentid" in ql.replace(" ", "") and "enrolment.studentid" in ql.replace(" ", ""), "Join the tables by matching Student.StudentID (primary key) with Enrolment.StudentID (foreign key)"
assert sorted(rows) == [("Ann", "Computing"), ("Ben", "Maths")], "The SELECT should give the Name and Course for each enrolment, [('Ann', 'Computing'), ('Ben', 'Maths')] in any order, but gave %r" % (rows,)
assert kinds.index("UPDATE") > kinds.index("SELECT"), "Put the UPDATE after the SELECT"
students = db.execute("select StudentID, Name from Student order by StudentID").fetchall()
assert students == [(1, "Anna"), (2, "Ben")], "After the UPDATE, Student should hold (1, 'Anna') and (2, 'Ben'), but holds %r" % (students,)
enrol = db.execute("select EnrolID, StudentID, Course from Enrolment order by EnrolID").fetchall()
assert enrol == [(1, 1, "Computing")], "After the DELETE, Enrolment should only hold (1, 1, 'Computing'), but holds %r" % (enrol,)
'''},

 {"slug": "relational-database-sqlite3", "title": "Relational database with sqlite3 (Python)", "fn": "Python script", "kind": "script", "group": "Others",
  "sample": '''import sqlite3

conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("CREATE TABLE Student (StudentID INTEGER PRIMARY KEY, Name TEXT, Grade TEXT)")
cur.execute("INSERT INTO Student VALUES (?, ?, ?)", (1, "Ann", "B"))
cur.execute("INSERT INTO Student VALUES (?, ?, ?)", (2, "Ben", "C"))
conn.commit()

cur.execute("SELECT Name, Grade FROM Student WHERE StudentID = ?", (1,))
row = cur.fetchone()
print(row)

cur.execute("UPDATE Student SET Grade = ? WHERE StudentID = ?", ("A", 2))
cur.execute("DELETE FROM Student WHERE StudentID = ?", (1,))
conn.commit()

cur.execute("SELECT * FROM Student")
rows = cur.fetchall()
print(rows)
conn.close()
''',
  "tests": '''import sqlite3 as _sq
_t = ast.parse(_SRC)
for _n in ast.walk(_t):
    if isinstance(_n, ast.Name) and isinstance(_n.ctx, ast.Store) and len(_n.id) == 1:
        raise AssertionError("Line %d: variable '%s' is a single letter. Use a meaningful name such as student or rec" % (_n.lineno, _n.id))
_names_used = _names(_SRC)
assert "connect" in _names_used and "sqlite3" in _names_used, "Use sqlite3.connect(...) to open the database"
assert any(n.value == "data.db" for n in ast.walk(_t) if isinstance(n, ast.Constant)), "Open the database file with sqlite3.connect('data.db')"
assert "commit" in _names_used, "Call conn.commit() after changing the data"
_sqls = [n.value.lower() for n in ast.walk(_t) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
assert sum(q.strip().startswith("create table") for q in _sqls) == 1, "Create exactly one table with CREATE TABLE"
for _k in ("insert into", "select", "update", "delete from"):
    assert any(q.strip().startswith(_k) for q in _sqls), "No %s statement found" % _k.upper()
assert any("?" in q for q in _sqls), "Use ? placeholders and pass the values as a tuple, not string joining"
assert "row" in globals(), "Store the result of fetchone() in a variable called row"
assert tuple(row) == ("Ann", "B"), "row should be ('Ann', 'B') from the SELECT with WHERE StudentID = 1, but is %r" % (row,)
assert "rows" in globals(), "Store the result of fetchall() in a variable called rows"
assert [tuple(r) for r in rows] == [(2, "Ben", "A")], "After the UPDATE (Ben's grade becomes 'A') and DELETE (Ann removed), rows should be [(2, 'Ben', 'A')] but is %r" % (rows,)
'''},
 {"slug": "web-app", "title": "Web app (Flask and Jinja)", "fn": "app.py and index.html", "kind": "webapp", "group": "Others",
  "sample": '''from flask import Flask, render_template, request

app = Flask(__name__)
students = []


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"]
        students.append(name)
    return render_template("index.html", students=students)


if __name__ == "__main__":
    app.run(debug=True)
''',
  "sample2": '''<!DOCTYPE html>
<html>
<head>
    <title>Students</title>
</head>
<body>
    <form method="post">
        <input type="text" name="name">
        <input type="submit" value="Add">
    </form>
    <table border="1">
        <tr>
            <th>No.</th>
            <th>Name</th>
        </tr>
        {% for student in students %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ student }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
''',
  "tests": '''import sys, re, types, traceback, jinja2
_routes = {}
class _Req:
    method = "GET"
    form = {}
request = _Req()
class _Flask:
    def __init__(self, name=None, *a, **k): pass
    def route(self, rule, methods=None, **k):
        def deco(f):
            _routes[rule] = (f, [m.upper() for m in (methods or ["GET"])])
            return f
        return deco
    def run(self, *a, **k): pass
def _render(name, **ctx):
    assert name == "index.html", "render_template should be given \\"index.html\\", not %r" % (name,)
    return jinja2.Environment(autoescape=True).from_string(_HTML).render(**ctx)
class _Redirect:
    def __init__(self, loc="/"): self.loc = loc
_fl = types.ModuleType("flask")
_fl.Flask = _Flask; _fl.request = request; _fl.render_template = _render
_fl.redirect = lambda loc="/", *a, **k: _Redirect(loc); _fl.url_for = lambda *a, **k: "/"
sys.modules["flask"] = _fl
try:
    _t = ast.parse(_SRC)
except SyntaxError as _e:
    raise AssertionError("app.py line %s: SyntaxError: %s" % (_e.lineno, _e.msg))
assert any(isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__" for n in _t.body), "app.py should end with if __name__ == \\"__main__\\": app.run(...)"
_g = {"__name__": "app_module"}
try:
    exec(compile(_SRC, "app.py", "exec"), _g)
except AssertionError:
    raise
except Exception as _e:
    _ln = [f.lineno for f in traceback.extract_tb(_e.__traceback__) if f.filename == "app.py"]
    raise AssertionError("app.py line %s: %s: %s" % (_ln[-1] if _ln else "?", type(_e).__name__, _e))
assert "/" in _routes, "app.py needs a route for \\"/\\" using @app.route(\\"/\\", methods=[\\"GET\\", \\"POST\\"])"
_view, _m = _routes["/"]
assert "GET" in _m and "POST" in _m, "The \\"/\\" route needs methods=[\\"GET\\", \\"POST\\"] so it can show the page and receive the form, found %r" % (_m,)
_h = _HTML
assert re.search(r"<form[^>]*method\\s*=\\s*[\\"']?post", _h, re.I), "index.html needs a <form method=\\"post\\">"
_tm = re.search(r"<input[^>]*type\\s*=\\s*[\\"']?text[^>]*>", _h, re.I)
assert _tm, "index.html needs an <input type=\\"text\\" name=\\"...\\"> text box"
_nm = re.search(r"name\\s*=\\s*[\\"']([^\\"']+)[\\"']", _tm.group(0))
assert _nm, "The text box needs a name attribute, e.g. name=\\"name\\", so the form can send it"
assert re.search(r"<input[^>]*type\\s*=\\s*[\\"']?submit", _h, re.I), "index.html needs an <input type=\\"submit\\"> button"
assert "{% for" in _h and "{% endfor" in _h, "index.html needs a Jinja {% for ... %} loop with {% endfor %}"
_lv = re.search(r"{%-?\\s*for\\s+(\\w+)\\s+in\\s", _h)
assert _lv and len(_lv.group(1)) > 1, "Do not use a single-letter loop variable. Write {% for student in students %}"
assert "{{" in _h, "The table rows must use Jinja data tags such as {{ student }}"
assert re.search(r"<table", _h, re.I) and re.search(r"<tr", _h, re.I) and re.search(r"<td", _h, re.I), "index.html needs a <table> with <tr> and <td> cells"
request.method = "GET"; request.form = {}
_r0 = _view()
assert isinstance(_r0, str), "The view should return render_template(...), got %r" % (type(_r0).__name__,)
assert "<td" not in _r0.lower(), "With nothing submitted the table should have no data rows, but the page already shows <td> cells"
for _v in ("Cai", "Dee"):
    request.method = "POST"; request.form = {_nm.group(1): _v}
    _view()
    request.method = "GET"; request.form = {}
    _r = _view()
    assert isinstance(_r, str), "The view should return the page after a GET"
    assert _v in _r, "After the form sends %r, the page should list it, but it does not. Check app.py stores request.form[%r] and passes the list to render_template, and the loop prints it" % (_v, _nm.group(1))
_cells = re.findall(r"<td[^>]*>(.*?)</td>", _r, re.S | re.I)
assert _r.index("Cai") < _r.index("Dee"), "Items should be listed in the order they were added"
assert sum(c.strip() == "Cai" or c.strip() == "Dee" for c in _cells) == 2, "Each submitted name should sit inside its own <td> in a table row, found cells %r" % (_cells,)
'''},
]
for _a in ALGOS:
    _a.setdefault("kind", "func"); _a.setdefault("group", "Algorithms")
for _a in STRUCTS:
    _a.setdefault("group", "Data structures")
ALGOS.extend(STRUCTS)
ALGOS.extend(OTHERS)
for _a in ALGOS:
    _a["pkgs"] = {"sql": ["sqlite3"], "script": ["sqlite3"], "webapp": ["jinja2"]}.get(_a["kind"], [])
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
    elif slug == "queue-array":
        if not any(isinstance(n, _ast.BinOp) and isinstance(n.op, _ast.Mod) for n in _ast.walk(tree)):
            notes.append("no wraparound with % found, which is what makes the array queue circular")
    elif slug == "binary-search-tree":
        if nclass < 2:
            notes.append("no separate node class with left and right links found")
    return notes


_INSTR_CACHE = {}
# Drills whose tests never insist on what happens when you remove from an empty structure.
EDGE_REMOVERS = {"stack": ("pop", "peek"), "queue": ("dequeue", "peek")}
_EMPTY_ERRORS = {"IndexError", "LookupError", "Exception", "BaseException"}

def edge_check(slug, code):
    """Static read (nothing is run) of how pop/peek/dequeue deal with an empty structure.
    Returns (missing, unresolved): lists of method names.
      missing    - no check that depends on the structure's own state was found, so removing from an
                   empty one would fail (conditions about other things and unrelated except clauses do not count)
      unresolved - something looks like a check but it cannot be confirmed from the code alone
    Handled cases (a state-based if/else that returns or raises, a one-line conditional, a slice, next(..., default),
    an except IndexError/Exception, or a helper method that does one of these) are in neither list."""
    names = EDGE_REMOVERS.get(slug)
    if not names:
        return [], []
    try:
        tree = _ast.parse(code)
    except SyntaxError:
        return [], []
    methods = {}
    for c in _ast.walk(tree):
        if isinstance(c, _ast.ClassDef):
            for f in c.body:
                if isinstance(f, _ast.FunctionDef):
                    methods.setdefault(f.name, f)
    def uses_self(node):
        return any(isinstance(n, _ast.Name) and n.id == "self" for n in _ast.walk(node))
    def state_names(f):
        out = set()
        for n in _ast.walk(f):
            if isinstance(n, _ast.Assign) and uses_self(n.value):
                for t in n.targets:
                    out |= {x.id for x in _ast.walk(t) if isinstance(x, _ast.Name)}
        return out
    def relevant(test, f):
        st = state_names(f)
        return uses_self(test) or any(isinstance(n, _ast.Name) and n.id in st for n in _ast.walk(test))
    def exits(nodes):
        return any(isinstance(n, (_ast.Return, _ast.Raise)) for b in nodes for n in _ast.walk(b))
    def classify(f, depth=0):
        """'ok', 'unresolved' or 'missing'"""
        weak = False
        for n in _ast.walk(f):
            if isinstance(n, _ast.If) and relevant(n.test, f):
                if exits(n.body) or exits(n.orelse):
                    return "ok"
                weak = True
            elif isinstance(n, _ast.IfExp) and relevant(n.test, f):
                return "ok"
            elif isinstance(n, _ast.BoolOp) and relevant(n, f):
                return "ok"
            elif isinstance(n, _ast.Try):
                for h in n.handlers:
                    t = h.type
                    ts = [] if t is None else (t.elts if isinstance(t, _ast.Tuple) else [t])
                    if t is None or any(isinstance(x, _ast.Name) and x.id in _EMPTY_ERRORS for x in ts):
                        return "ok"
                    weak = weak or False
            elif isinstance(n, _ast.Subscript) and isinstance(n.slice, _ast.Slice) and uses_self(n):
                return "ok"
            elif (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name) and n.func.id == "next"
                  and len(n.args) + len(n.keywords) >= 2):
                return "ok"
        if depth < 2:
            for n in _ast.walk(f):
                if (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute) and isinstance(n.func.value, _ast.Name)
                        and n.func.value.id == "self" and n.func.attr in methods and methods[n.func.attr] is not f):
                    r = classify(methods[n.func.attr], depth + 1)
                    if r == "ok":
                        return "ok"
                    weak = weak or r == "unresolved"
        return "unresolved" if weak else "missing"
    missing, unresolved = [], []
    for m in names:
        if m in methods:
            r = classify(methods[m])
            (missing if r == "missing" else unresolved if r == "unresolved" else []).append(m)
    return missing, unresolved

def edge_notes(slug, code):
    """Teacher-review notes for methods where no empty check was found (see edge_check)."""
    what = "stack" if slug == "stack" else "queue"
    miss = edge_check(slug, code)[0]
    return ["%s - no check for an empty %s found (automatic read, confirm in the code)" % (", ".join(m + "()" for m in miss), what)] if miss else []

def instrument(slug):
    """Competition progress marks: after every assert in the checker add _CK.add(n). Returns (tests_text, total_asserts).
    A failed run's progress = distinct asserts that passed / total. Checks stop at the first failure, so it is a rough guide."""
    if slug in _INSTR_CACHE:
        return _INSTR_CACHE[slug]
    import ast as _a
    tree = _a.parse(BY_SLUG[slug]["tests"])
    counter = [0]
    class T(_a.NodeTransformer):
        def generic_visit(self, node):
            node = super().generic_visit(node)
            for field in ("body", "orelse", "finalbody"):
                seq = getattr(node, field, None)
                if isinstance(seq, list):
                    new = []
                    for st in seq:
                        new.append(st)
                        if isinstance(st, _a.Assert):
                            n = counter[0]; counter[0] += 1
                            new.append(_a.parse("_CK.add(%d)" % n).body[0])
                    setattr(node, field, new)
            return node
    tree = T().visit(tree)
    _a.fix_missing_locations(tree)
    out = (_a.unparse(tree), counter[0])
    _INSTR_CACHE[slug] = out
    return out
