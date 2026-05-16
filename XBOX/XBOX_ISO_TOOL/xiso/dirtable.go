package xiso

import (
	"strings"
)

func cmpName(a, b string) int {
	ua := strings.ToUpper(a)
	ub := strings.ToUpper(b)
	return strings.Compare(ua, ub)
}

type Node struct {
	Left   int
	Right  int
	Parent int
	Height int
	Name   string
	Size   uint32
	Attr   uint8
	Index  int 
}

type Tree struct {
	nodes []Node
	root  int
}

func NewTree() *Tree {
	return &Tree{root: -1}
}

func (t *Tree) Len() int { return len(t.nodes) }

func (t *Tree) Insert(name string, size uint32, attr uint8) bool {
	idx := len(t.nodes)
	n := Node{
		Left:   -1,
		Right:  -1,
		Parent: -1,
		Height: 1,
		Name:   name,
		Size:   size,
		Attr:   attr,
		Index:  idx,
	}

	if t.root == -1 {
		t.nodes = append(t.nodes, n)
		t.root = 0
		return true
	}

	cur := t.root
	for {
		c := cmpName(name, t.nodes[cur].Name)
		if c == 0 {
			return false // duplicate
		}
		if c < 0 {
			if t.nodes[cur].Left == -1 {
				t.nodes[cur].Left = idx
				n.Parent = cur
				t.nodes = append(t.nodes, n)
				t.rebalance(idx)
				return true
			}
			cur = t.nodes[cur].Left
		} else {
			if t.nodes[cur].Right == -1 {
				t.nodes[cur].Right = idx
				n.Parent = cur
				t.nodes = append(t.nodes, n)
				t.rebalance(idx)
				return true
			}
			cur = t.nodes[cur].Right
		}
	}
}

func (t *Tree) Height(idx int) int {
	if idx == -1 {
		return 0
	}
	return t.nodes[idx].Height
}

func (t *Tree) updateHeight(idx int) {
	if idx == -1 {
		return
	}
	lh := t.Height(t.nodes[idx].Left)
	rh := t.Height(t.nodes[idx].Right)
	h := lh
	if rh > h {
		h = rh
	}
	t.nodes[idx].Height = h + 1
}

func (t *Tree) balanceFactor(idx int) int {
	return t.Height(t.nodes[idx].Left) - t.Height(t.nodes[idx].Right)
}

func (t *Tree) parentDir(idx int) int {
	if idx == -1 {
		return 0
	}
	p := t.nodes[idx].Parent
	if p == -1 {
		return 0
	}
	if t.nodes[p].Left == idx {
		return -1 // left
	}
	return 1 // right
}

func (t *Tree) setChild(parent, child int, isLeft bool) {
	if isLeft {
		t.nodes[parent].Left = child
	} else {
		t.nodes[parent].Right = child
	}
	if child != -1 {
		t.nodes[child].Parent = parent
	}
}

func (t *Tree) rotateLeft(a int) {
	b := t.nodes[a].Right
	if b == -1 {
		return
	}

	bLeft := t.nodes[b].Left
	isA := t.parentDir(a)
	p := t.nodes[a].Parent

	t.nodes[a].Right = bLeft
	if bLeft != -1 {
		t.nodes[bLeft].Parent = a
	}
	t.nodes[b].Left = a
	t.nodes[a].Parent = b

	if p == -1 {
		t.root = b
		t.nodes[b].Parent = -1
	} else {
		t.setChild(p, b, isA == -1)
	}

	t.updateHeight(a)
	t.updateHeight(b)
}

func (t *Tree) rotateRight(a int) {
	b := t.nodes[a].Left
	if b == -1 {
		return
	}

	bRight := t.nodes[b].Right
	isA := t.parentDir(a)
	p := t.nodes[a].Parent

	t.nodes[a].Left = bRight
	if bRight != -1 {
		t.nodes[bRight].Parent = a
	}
	t.nodes[b].Right = a
	t.nodes[a].Parent = b

	if p == -1 {
		t.root = b
		t.nodes[b].Parent = -1
	} else {
		t.setChild(p, b, isA == -1)
	}

	t.updateHeight(a)
	t.updateHeight(b)
}

func (t *Tree) rebalance(leaf int) {
	cur := leaf
	for cur != -1 {
		t.updateHeight(cur)
		bf := t.balanceFactor(cur)

		if bf > 1 {
			if t.balanceFactor(t.nodes[cur].Left) < 0 {
				t.rotateLeft(t.nodes[cur].Left)
			}
			t.rotateRight(cur)
		} else if bf < -1 {
			if t.balanceFactor(t.nodes[cur].Right) > 0 {
				t.rotateRight(t.nodes[cur].Right)
			}
			t.rotateLeft(cur)
		}

		cur = t.nodes[cur].Parent
	}
}

func (t *Tree) Preorder() []int {
	if t.root == -1 {
		return nil
	}
	var result []int
	stack := []int{t.root}
	for len(stack) > 0 {
		top := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		result = append(result, top)
		if t.nodes[top].Right != -1 {
			stack = append(stack, t.nodes[top].Right)
		}
		if t.nodes[top].Left != -1 {
			stack = append(stack, t.nodes[top].Left)
		}
	}
	return result
}

func (t *Tree) Get(idx int) *Node {
	return &t.nodes[idx]
}
