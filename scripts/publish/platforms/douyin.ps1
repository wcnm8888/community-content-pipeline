function Invoke-DouyinPublish {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    $spec = [pscustomobject]@{
        Key = "douyin"
        Url = "https://creator.douyin.com/creator-micro/content/publish"
        CoverRatio = "3:4"
        EntryHints = @("发布文章", "一键导入", "文章摘要", "文章正文", "标题", "话题", "封面")
        ManualBeforeDraft = "请确认当前处于抖音发布文章页；如果提示继续编辑上次未发布文章，请先手动清理旧草稿或确认继续后按 Enter。"
        PreClickTexts = @()
        ImportMarkdown = $true
        ImportKind = "douyin"
        ImportClickTexts = @("发布文章", "一键导入", "点击上传", "上传文档")
        SkipBodyFillAfterImport = $true
        CoverClickTexts = @("上传图片", "上传封面", "选择封面", "编辑封面")
        SaveDraftTexts = @("保存草稿", "存草稿")
        SaveOptional = $false
        PublishTexts = @("发布", "立即发布")
        Selectors = [pscustomobject]@{
            title = @(
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']",
                "input[placeholder*='添加标题']",
                "textarea[placeholder*='添加标题']"
            )
            body = @()
            summary = @(
                "textarea[placeholder*='简介']",
                "textarea[placeholder*='摘要']",
                "textarea[placeholder*='描述']",
                "input[placeholder*='简介']"
            )
            topics = @()
            tags = @()
            hashtags = @(
                "input[placeholder*='话题']",
                "input[placeholder*='添加话题']",
                "input[placeholder*='#']"
            )
        }
    }

    Invoke-GenericPlatform $Context $spec $Pack
}
