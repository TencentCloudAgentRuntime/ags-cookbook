# Agent Sandbox Cookbook

A comprehensive guide and example collection for Agent Sandbox.

## Introduction

Agent Sandbox Cookbook is a comprehensive guide and example collection demonstrating how to build powerful AI Agent applications using Agent Sandbox through existing SDKs. This project includes a complete learning path from basic tutorials to advanced examples.

## Project Structure

```
ags-cookbook/
├── .gitignore                              
├── LICENSE                                 
├── README.md                               # Project documentation
├── CODE_OF_CONDUCT.md                      # Code of conduct
├── CONTRIBUTING.md                         # Contributing guidelines
├── benchmarks/                             # Performance benchmarks
│   └── k6/                                # K6 load testing scripts
│       ├── README.md
│       ├── sandbox-stress-test.js
│       ├── sandbox-stress-test-data-plane.js
│       ├── sandbox-stress-test-e2b-api.js
│       └── sandbox-stress-test-non-exec.js
├── tutorials/                              # Tutorial documents
│   ├── sdk/
│   │   ├── e2b/
│   │   │   ├── e2b_base.ipynb            # E2B SDK basics (includes code sandbox tutorial)
│   │   │   └── browser_vnc.ipynb         # Browser sandbox tutorial
│   │   └── go/
│   │       ├── README.md
│   │       └── example_test.go           # Go SDK examples
│   └── yunapi/
│       └── python/
│           └── custom.ipynb              # Custom API tutorial
└── examples/                               # Example code
    ├── README.md                          
    ├── browser-agent/                     # Browser automation agent example
    │   ├── README.md                      
    │   ├── main.py          
    │   └── pyproject.toml               
    ├── data-analysis/                     # Data analysis example
    │   ├── README.md                      
    │   ├── multi_context_demo.py          
    │   └── requirements.txt               
    ├── html-processing/                   # HTML collaboration example
    │   ├── README.md                      
    │   ├── html_collaboration_demo.py     
    │   └── requirements.txt               
    ├── mini-rl/                           # Mini reinforcement learning example
    │   ├── README.md                      
    │   ├── main.py          
    │   └── pyproject.toml               
    ├── mobile-use/                        # Mobile automation example
    │   ├── README.md                      
    │   ├── quickstart.py                  # Quick start example
    │   ├── batch.py                       # Batch operations (multi-process + async)
    │   ├── sandbox_connect.py             # Single sandbox connection tool (CLI)
    │   └── requirements.txt               
    ├── shop-assistant/                    # Shopping cart automation example
    │   ├── README.md                      
    │   ├── automation_cart_demo.py        
    │   └── requirements.txt               
    └── swe-agent/                         # SWE-agent with AGS integration example
        ├── README.md                      
        ├── README_zh.md                   
        └── SWE-ReX/                       # Modified SWE-ReX for AGS integration

## Key Features

### Multi-Sandbox Collaboration
- **Code + Browser Collaboration**: Seamless collaboration between code sandbox and browser sandbox
- **Multi-Context Environment Isolation**: Each Context has its own independent variable space
- **File System Integration**: Data transfer between sandboxes via file system

### Complex Data Processing Demo
- **Large-scale Dataset Processing**: Support for processing thousands of data records
- **Complete Data Cleaning Pipeline**: Outlier handling, feature engineering, data quality optimization
- **Professional Division of Labor**: Collaboration between data preprocessing, analysis, and visualization experts

### Web Development & Automation
- **Dynamic HTML Editing**: Programmatic modification of web content
- **Visual Verification**: Verify editing effects through screenshot comparison
- **Browser Automation**: Support for complex web interactions

### Professional Data Visualization
- **Before/After Data Cleaning Comparison**: Intuitive display of cleaning effects
- **Comprehensive Business Dashboard**: Multi-dimensional data analysis charts
- **Correlation Heatmap**: Business metric correlation analysis

## Quick Start

### Requirements
- Python 3.8+

### Environment Configuration

```bash
export E2B_API_KEY="your-api-key-here"
export E2B_DOMAIN="tencentags.com"  # Optional, uses this domain by default
```

### Running Examples

Each example has independent dependency management. Please refer to the documentation in the specific example directory.

## User Guide

### 1. Basic Tutorials

**Code Interpreter Sandbox** - `tutorials/sdk/e2b/e2b_base.ipynb`
- Create and manage sandbox environments
- Execute code and handle results
- File upload and download
- Multi-Context environment isolation

**Browser Sandbox** - `tutorials/sdk/e2b/browser_vnc.ipynb`
- VNC visual interface operations
- Playwright programmatic control
- File system and browser integration
- Cookie and session management

### 2. Advanced Examples

**Data Analysis Example** - `examples/data-analysis/`
- Multi-Context collaboration for complex data processing
- Complete data cleaning and analysis pipeline
- Professional data visualization charts

**HTML Collaboration Example** - `examples/html-processing/`
- Code sandbox and Browser sandbox collaboration
- Dynamic HTML editing and visual verification
- Web development workflow demonstration

**Shopping Cart Automation Example** - `examples/shop-assistant/`
- E-commerce add-to-cart flow with login state
- Cookie import for login-free access
- Remote browser control and debugging

## Technical Architecture

### Sandbox Environment
- **Code Interpreter Sandbox**: Supports multiple languages including Python, JavaScript, R
- **Browser Sandbox**: Built-in browser with VNC and Playwright control support
- **Isolated Execution**: Each code block runs in an independent environment
- **Persistent Storage**: Supports file system operations and data persistence
- **Sandbox Collaboration**: Different sandbox types can collaborate via file system

### Dependency Management
- **Modular Dependencies**: Each example has its own `requirements.txt`
- **Version Isolation**: Avoids dependency conflicts between different examples
- **On-demand Installation**: Only install dependencies required for the current example

## Contributing

We welcome new examples and tutorials!

1. Fork this repository
2. Create a feature branch: `git checkout -b feature/new-example`
3. Commit your changes: `git commit -am 'Add new example'`
4. Create a Pull Request

### Example Contribution Guidelines

New examples should follow this structure:
```
examples/your-example-name/
├── README.md              # Detailed documentation
├── main_script.py         # Main demo script
└── requirements.txt       # Example-specific dependencies
```

Each example should include:
- **README.md**: Feature description, use cases, running steps, expected output
- **Complete running instructions**: Complete steps from dependency installation to execution
- **Independent dependency management**: Use a dedicated `requirements.txt`
- **Clear output description**: Describe generated files and expected results

## License

This project is open-sourced under the Apache 2.0 License. See the [LICENSE](LICENSE-Agent%20Sandbox%20Cookbook.txt) file for details.
