package spinner

import (
	"fmt"
	"sync"

	"github.com/charmbracelet/bubbles/spinner"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// TaskStatus 任务状态
type TaskStatus int

const (
	TaskStatusPending TaskStatus = iota
	TaskStatusRunning
	TaskStatusSuccess
	TaskStatusFailed
)

// Task 表示一个预热任务
type Task struct {
	ID      string
	Name    string
	Status  TaskStatus
	Message string
}

// AddTaskMsg 添加任务消息
type AddTaskMsg struct {
	ID   string
	Name string
}

// UpdateTaskMsg 更新任务状态消息
type UpdateTaskMsg struct {
	ID      string
	Status  TaskStatus
	Message string
}

// QuitMsg 退出消息
type QuitMsg struct{}

// sharedState 共享状态，避免锁拷贝
type sharedState struct {
	mu         sync.RWMutex
	tasks      map[string]*Task
	taskOrder  []string
	completed  int
	failed     int
	totalAdded int
}

// Model 是 spinner TUI 的模型
type Model struct {
	state    *sharedState
	spinner  spinner.Model
	quitting bool
}

var (
	spinnerStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("69"))
	successStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("42"))
	failedStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("196"))
	pendingStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
	titleStyle   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
)

// New 创建一个新的 spinner 模型
func New() Model {
	s := spinner.New()
	s.Spinner = spinner.Dot
	s.Style = spinnerStyle
	return Model{
		state: &sharedState{
			tasks:     make(map[string]*Task),
			taskOrder: make([]string, 0),
		},
		spinner: s,
	}
}

func (m Model) Init() tea.Cmd {
	return m.spinner.Tick
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			m.quitting = true
			return m, tea.Quit
		}

	case AddTaskMsg:
		m.state.mu.Lock()
		if _, exists := m.state.tasks[msg.ID]; !exists {
			task := &Task{
				ID:     msg.ID,
				Name:   msg.Name,
				Status: TaskStatusRunning,
			}
			m.state.tasks[msg.ID] = task
			m.state.taskOrder = append(m.state.taskOrder, msg.ID)
			m.state.totalAdded++
		}
		m.state.mu.Unlock()
		return m, nil

	case UpdateTaskMsg:
		m.state.mu.Lock()
		if task, exists := m.state.tasks[msg.ID]; exists {
			oldStatus := task.Status
			task.Status = msg.Status
			task.Message = msg.Message

			// 更新计数
			if oldStatus != TaskStatusSuccess && msg.Status == TaskStatusSuccess {
				m.state.completed++
			}
			if oldStatus != TaskStatusFailed && msg.Status == TaskStatusFailed {
				m.state.failed++
			}
		}
		m.state.mu.Unlock()
		return m, nil

	case QuitMsg:
		m.quitting = true
		return m, tea.Quit

	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	return m, nil
}

func (m Model) View() string {
	if m.quitting {
		return m.finalView()
	}

	m.state.mu.RLock()
	defer m.state.mu.RUnlock()

	var s string

	// 标题和统计
	total := m.state.totalAdded
	running := total - m.state.completed - m.state.failed
	s += titleStyle.Render(fmt.Sprintf("镜像预热进度: %d/%d 完成", m.state.completed, total))
	s += fmt.Sprintf(" (运行中: %d, 失败: %d)\n\n", running, m.state.failed)

	// 显示任务列表（最多显示最近 15 个）
	displayCount := 15
	startIdx := 0
	if len(m.state.taskOrder) > displayCount {
		startIdx = len(m.state.taskOrder) - displayCount
	}

	for i := startIdx; i < len(m.state.taskOrder); i++ {
		id := m.state.taskOrder[i]
		task := m.state.tasks[id]
		if task == nil {
			continue
		}

		var line string
		switch task.Status {
		case TaskStatusRunning:
			line = fmt.Sprintf("%s %s", m.spinner.View(), task.Name)
		case TaskStatusSuccess:
			line = successStyle.Render(fmt.Sprintf("✓ %s", task.Name))
		case TaskStatusFailed:
			msg := task.Message
			if len(msg) > 50 {
				msg = msg[:50] + "..."
			}
			line = failedStyle.Render(fmt.Sprintf("✗ %s: %s", task.Name, msg))
		case TaskStatusPending:
			line = pendingStyle.Render(fmt.Sprintf("○ %s", task.Name))
		}
		s += line + "\n"
	}

	if startIdx > 0 {
		s += pendingStyle.Render(fmt.Sprintf("  ... 还有 %d 个任务\n", startIdx))
	}

	s += "\n" + pendingStyle.Render("按 q 退出")
	return s
}

func (m Model) finalView() string {
	m.state.mu.RLock()
	defer m.state.mu.RUnlock()

	return fmt.Sprintf("\n%s\n完成: %d, 失败: %d, 总计: %d\n",
		titleStyle.Render("预热任务完成"),
		m.state.completed, m.state.failed, m.state.totalAdded)
}

// Manager 管理 spinner TUI 和任务
type Manager struct {
	program *tea.Program
}

// NewManager 创建一个新的 Manager
func NewManager() *Manager {
	model := New()
	return &Manager{
		program: tea.NewProgram(model),
	}
}

// Start 启动 TUI
func (m *Manager) Start() error {
	_, err := m.program.Run()
	return err
}

// AddTask 添加一个任务
func (m *Manager) AddTask(id, name string) {
	m.program.Send(AddTaskMsg{ID: id, Name: name})
}

// UpdateTask 更新任务状态
func (m *Manager) UpdateTask(id string, status TaskStatus, message string) {
	m.program.Send(UpdateTaskMsg{ID: id, Status: status, Message: message})
}

// FinishTask 标记任务完成
func (m *Manager) FinishTask(id string) {
	m.UpdateTask(id, TaskStatusSuccess, "")
}

// FailTask 标记任务失败
func (m *Manager) FailTask(id, message string) {
	m.UpdateTask(id, TaskStatusFailed, message)
}

// Quit 退出 TUI
func (m *Manager) Quit() {
	m.program.Send(QuitMsg{})
}
