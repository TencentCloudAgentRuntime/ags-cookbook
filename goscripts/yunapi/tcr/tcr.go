package tcr

import (
	"context"
	"iter"

	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	tcr "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/tcr/v20190924"
	"golang.org/x/time/rate"

	"goscripts/config"
)

const (
	defaultPageSize = int64(100)
)

// Client TCR 客户端封装
type Client struct {
	tencentCloud *tcr.Client
	rateLimiter  *rate.Limiter
}

// NewClient 创建 TCR 客户端
func NewClient() (*Client, error) {
	credential := common.NewCredential(
		config.C.TencentCloud.SecretID,
		config.C.TencentCloud.SecretKey,
	)
	client, err := tcr.NewClient(
		credential,
		config.C.TencentCloud.Region,
		profile.NewClientProfile(),
	)
	if err != nil {
		return nil, err
	}
	return &Client{
		tencentCloud: client,
		rateLimiter:  rate.NewLimiter(rate.Limit(100), 100),
	}, nil
}

// Repositories 查询命名空间下的所有镜像仓库，支持 for range 遍历
func (c *Client) Repositories(ctx context.Context, registryID, namespace string) iter.Seq2[*tcr.TcrRepositoryInfo, error] {
	return func(yield func(*tcr.TcrRepositoryInfo, error) bool) {
		var offset int64 = 1
		for {
			select {
			case <-ctx.Done():
				yield(nil, ctx.Err())
				return
			default:
			}

			req := tcr.NewDescribeRepositoriesRequest()
			req.RegistryId = common.StringPtr(registryID)
			req.NamespaceName = common.StringPtr(namespace)
			req.Offset = common.Int64Ptr(offset)
			req.Limit = common.Int64Ptr(defaultPageSize)

			if err := c.rateLimiter.Wait(ctx); err != nil {
				yield(nil, err)
				return
			}
			resp, err := c.tencentCloud.DescribeRepositoriesWithContext(ctx, req)
			if err != nil {
				yield(nil, err)
				return
			}

			for _, repo := range resp.Response.RepositoryList {
				if !yield(repo, nil) {
					return
				}
			}

			// 检查是否还有更多数据
			if resp.Response.TotalCount == nil || offset*defaultPageSize >= *resp.Response.TotalCount {
				return
			}
			offset++
		}
	}
}

// RepositoryImages 查询镜像仓库下的所有镜像，支持 for range 遍历
func (c *Client) RepositoryImages(ctx context.Context, registryID, namespace, repository string) iter.Seq2[*tcr.TcrImageInfo, error] {
	return func(yield func(*tcr.TcrImageInfo, error) bool) {
		var offset int64 = 1
		for {
			select {
			case <-ctx.Done():
				yield(nil, ctx.Err())
				return
			default:
			}

			req := tcr.NewDescribeImagesRequest()
			req.RegistryId = common.StringPtr(registryID)
			req.NamespaceName = common.StringPtr(namespace)
			req.RepositoryName = common.StringPtr(repository)
			req.Offset = common.Int64Ptr(offset)
			req.Limit = common.Int64Ptr(defaultPageSize)

			if err := c.rateLimiter.Wait(ctx); err != nil {
				yield(nil, err)
				return
			}
			resp, err := c.tencentCloud.DescribeImagesWithContext(ctx, req)
			if err != nil {
				yield(nil, err)
				return
			}

			for _, image := range resp.Response.ImageInfoList {
				if !yield(image, nil) {
					return
				}
			}

			// 检查是否还有更多数据
			if resp.Response.TotalCount == nil || offset*defaultPageSize >= *resp.Response.TotalCount {
				return
			}
			offset++
		}
	}
}

// DescribeInstance 根据 registry ID 获取 TCR 实例信息
func (c *Client) DescribeInstance(ctx context.Context, registryID string) (*tcr.Registry, error) {
	if err := c.rateLimiter.Wait(ctx); err != nil {
		return nil, err
	}

	req := tcr.NewDescribeInstancesRequest()
	req.Registryids = common.StringPtrs([]string{registryID})

	resp, err := c.tencentCloud.DescribeInstancesWithContext(ctx, req)
	if err != nil {
		return nil, err
	}

	if len(resp.Response.Registries) == 0 {
		return nil, nil
	}

	return resp.Response.Registries[0], nil
}
