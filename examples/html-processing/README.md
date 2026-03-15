# HTML Collaboration Demo

**Code + Browser Sandbox Collaboration** - Demonstrates complete workflow of HTML creation, editing, and rendering

## Features

- **Dual Sandbox Collaboration**: Code sandbox editing + Browser sandbox rendering
- **Visual Comparison**: Before/after screenshot comparison
- **Complete Workflow**: Create → Render → Edit → Re-render
- **File Transfer**: Local ↔ Browser ↔ Code ↔ Browser ↔ Local

## Business Scenario

Simulates common collaboration scenarios in web development:
- Designer creates HTML template
- Developer programmatically modifies content
- Real-time preview of modifications
- Generate before/after comparison screenshots

## Execution Flow

### 1. Local HTML Creation
- Create responsive HTML page with gradient background
- Include timestamp and style design
- Save as `demo.html`

### 2. Browser Sandbox First Render
- Upload HTML to Browser sandbox
- Render page using Playwright
- Generate `screenshot_before.png`

### 3. Code Sandbox HTML Editing
- Transfer HTML file to Code sandbox
- Execute Python code for content editing
- Add "Edit by Code Interpreter Sandbox" identifier
- Generate `demo_edited.html`

### 4. Browser Sandbox Re-render
- Upload edited HTML to Browser sandbox
- Render again and take screenshot
- Generate `screenshot_after.png`

### 5. Result Comparison
- Download all files to local
- Generate before/after comparison screenshots
- Intuitively display editing effects

## Output Files

4 files generated after running:
- `demo.html` - **Original HTML file**
- `demo_edited.html` - **HTML edited by Code sandbox**
- `screenshot_before.png` - **Page screenshot before editing**
- `screenshot_after.png` - **Page screenshot after editing**

## Running Instructions

```bash
# Set environment variables
export E2B_DOMAIN='tencentags.com'
export E2B_API_KEY='your_ags_api_key'  # provided by Tencent Cloud Agent Sandbox product

# Install dependencies
pip install -r requirements.txt

# Run demo
python html_collaboration_demo.py

# View results
ls html_collaboration_output/
```

## Collaboration Flow Diagram

```
Local HTML Creation
     ↓
Browser Sandbox → Screenshot 1 (Original effect)
     ↓
Code Sandbox Edit → Add new content
     ↓
Browser Sandbox → Screenshot 2 (Edited effect)
     ↓
Local Comparison → Visually see differences
```

## Technical Highlights

### 1. Dual Sandbox Collaboration
- **Browser Sandbox**: Focused on rendering and screenshots
- **Code Sandbox**: Focused on code editing and processing
- **File System**: Acts as communication bridge between sandboxes

### 2. Real-time Edit Verification
- Programmatic HTML content modification
- Dynamic timestamp and identifier addition
- Preserve original styles and structure

### 3. Visual Comparison
- Pixel-level screenshot comparison
- Intuitive display of editing effects
- Support for complex page layouts

### 4. Complete Workflow
- End-to-end processing flow
- Automated file management
- Error handling and resource cleanup

## Extended Applications

Based on this example, you can extend:
- **Multi-round Editing**: Continuous multiple edits and renders
- **Style Optimization**: Automatic CSS optimization and beautification
- **Content Generation**: AI-generated HTML content
- **A/B Testing**: Multi-version page comparison
- **Responsive Testing**: Screenshots at different screen sizes

## Practical Use Cases

- **Web Development Debugging**: Quickly verify HTML modification effects
- **Automated Testing**: Visual regression testing for page changes
- **Content Management**: Batch processing of HTML templates
- **Design Verification**: Comparison of design mockups with actual effects
- **Document Generation**: Dynamic HTML report generation

## Quick Start

```bash
make run
```

