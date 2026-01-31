package ags

// PreCache 镜像预热相关接口

// CreatePreCacheImageTaskRequest 创建镜像预热任务请求参数
type CreatePreCacheImageTaskRequest struct {
	Image             string `json:"Image"`             // 镜像地址，如 "nginx:latest"
	ImageRegistryType string `json:"ImageRegistryType"` // 镜像仓库类型，如 "TCR"
}

// CreatePreCacheImageTaskResponse 创建镜像预热任务响应
type CreatePreCacheImageTaskResponse struct {
	Response struct {
		Image             string `json:"Image"` // 镜像地址
		ImageDigest       string `json:"ImageDigest"`
		ImageRegistryType string `json:"ImageRegistryType"`
		RequestId         string `json:"RequestId"` // 请求ID
	} `json:"Response"`
}

// CreatePreCacheImageTask 创建镜像预热任务
func (c *Client) CreatePreCacheImageTask(req *CreatePreCacheImageTaskRequest) (*CreatePreCacheImageTaskResponse, error) {
	params := map[string]any{
		"Image":             req.Image,
		"ImageRegistryType": req.ImageRegistryType,
	}

	var resp CreatePreCacheImageTaskResponse
	if err := c.CallWithResponse("CreatePreCacheImageTask", params, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// DescribePreCacheImageTaskRequest 查询镜像预热任务请求参数
type DescribePreCacheImageTaskRequest struct {
	Image             string  `json:"Image"`                 // 镜像地址
	ImageDigest       *string `json:"ImageDigest,omitempty"` // 镜像摘要，如 "sha256:abcdefg123..."
	ImageRegistryType string  `json:"ImageRegistryType"`     // 镜像仓库类型，如 "TCR"
}

// DescribePreCacheImageTaskResponse 查询镜像预热任务响应
type DescribePreCacheImageTaskResponse struct {
	Response struct {
		Image             string `json:"Image"`
		ImageDigest       string `json:"ImageDigest"`
		ImageRegistryType string `json:"ImageRegistryType"`
		Status            string `json:"Status"`
		Message           string `json:"Message"`
		RequestId         string `json:"RequestId"`
	} `json:"Response"`
}

// DescribePreCacheImageTask 查询镜像预热任务
func (c *Client) DescribePreCacheImageTask(req *DescribePreCacheImageTaskRequest) (*DescribePreCacheImageTaskResponse, error) {
	params := map[string]any{
		"Image":             req.Image,
		"ImageRegistryType": req.ImageRegistryType,
	}
	if req.ImageDigest != nil {
		params["ImageDigest"] = *req.ImageDigest
	}

	var resp DescribePreCacheImageTaskResponse
	if err := c.CallWithResponse("DescribePreCacheImageTask", params, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}
