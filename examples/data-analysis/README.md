# Data Analysis Example

This directory contains advanced usage examples for Agent Sandbox.

## multi_context_demo.py

**Multi-Context Collaboration Demo** - Demonstrates true environment isolation and professional division of labor

### Features

- **3 Completely Isolated Contexts**: Data preprocessing → Analysis → Visualization
- **5000-Product E-commerce Data**: Complex business scenario simulation
- **Data Cleaning Effect Comparison**: Before/after cleaning visualization
- **Professional Visualization Charts**: Business dashboard, heatmap, correlation analysis

### Business Scenario

Simulates product portfolio optimization for a multinational e-commerce platform:
- 5000 SKUs, 7 categories, 6 global markets
- Annual revenue of $1.88 million, average customer rating 4.21/5.0
- Identifies and removes 5.9% of loss-making products
- Profit margin optimized to 26.6%

### Execution Flow

1. **Context 1 - Data Preprocessing Expert**
   - Read raw data (5000 records)
   - Data quality check and cleaning
   - Remove loss-making products (295 SKUs)
   - Feature engineering: price tiers, performance scores

2. **Context 2 - Senior Data Analyst**
   - Verify environment isolation (cannot access Context 1 variables)
   - Group analysis: by category, region statistics
   - Correlation analysis: 6 key metrics
   - Significance testing: ANOVA variance analysis

3. **Context 3 - Data Visualization Master**
   - Dual isolation verification (cannot access previous two Context variables)
   - Before/after data cleaning comparison charts
   - Comprehensive business dashboard
   - Feature correlation heatmap

### Output Files

7 files generated after running:
- `data_cleaning_comparison.png` - **Data cleaning effect comparison**
- `advanced_dashboard.png` - Comprehensive business dashboard
- `correlation_heatmap.png` - Feature correlation analysis
- `analysis_report.json` - Detailed analysis report
- `cleaned_data.csv` - Cleaned dataset
- `complex_input_data.csv` - Raw dataset
- `data_quality_report.json` - Data quality report

### Running Instructions

```bash
# Set environment variables
export E2B_DOMAIN='tencentags.com'
export E2B_API_KEY='your_ags_api_key'  # provided by Tencent Cloud Agent Sandbox product

# Run demo
python multi_context_demo.py

# View results
ls enhanced_demo_output/
```

### Key Chart Interpretation

#### 1. Data Cleaning Comparison Chart (Top Left)
- **Red**: Distribution before cleaning
- **Blue**: Distribution after cleaning
- **Focus**: Profit margin changes from having negative values to completely positive

#### 2. Regional Performance Heatmap (Top Right)
- **Shows**: Percentage relative to average for each region
- **Interpretation**: >100% above average, <100% below average
- **Insight**: North America leads revenue by 8%, Middle East underperforms

#### 3. Data Quality Metrics (Bottom Left)
- **Product Count**: 5000 → 4705 (reduced by 295)
- **Loss-making Products**: 295 → 0 (completely eliminated)
- **Quantified Effect**: Specific improvements from data cleaning

#### 4. Price Tier Features (Bottom Right)
- **New Features**: Budget, Economy, Mid-range, Premium, Luxury
- **Business Value**: Conversion from price values to meaningful tiers

### Learning Points

1. **Environment Isolation Verification**: Observe how each Context verifies inability to access other Context variables
2. **Data Flow Mechanism**: Communication between Contexts via file system
3. **Business Value Realization**: From technical demo to actual business decision support
4. **Visualization Design**: How to design meaningful comparison charts
5. **Error Handling**: Exception handling and resource management in sandbox environment

### Custom Extensions

Based on this example, you can extend:
- Add new Contexts (e.g., machine learning expert)
- Modify business scenarios (e.g., finance, healthcare)
- Add more visualization charts
- Integrate external data sources
- Implement real-time data processing

## Quick Start

```bash
make run
```

