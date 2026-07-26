function Invoke-XiaohongshuPublish {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    $spec = [pscustomobject]@{
        Key = "xiaohongshu"
        Url = "https://creator.xiaohongshu.com/publish/publish?from=menu&target=article"
        CoverRatio = "3:4"
        EntryHints = @("发布笔记", "写长文", "文档导入", "标题", "话题", "图片编辑", "封面")
        ManualBeforeDraft = "请确认当前是小红书文章/写长文编辑页，能看到文档导入按钮；导入后如需一键排版，请手动完成再按 Enter。"
        PreClickTexts = @()
        ImportMarkdown = $true
        ImportClickTexts = @("文档导入", "导入", "点击或拖拽上传", "上传")
        SkipBodyFillAfterImport = $true
        CoverClickTexts = @("图片编辑", "添加封面", "上传封面", "点击上传封面图")
        SaveDraftTexts = @("保存草稿", "存草稿")
        SaveOptional = $true
        PublishTexts = @("发布", "立即发布")
        Selectors = [pscustomobject]@{
            title = @(
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']",
                "input[placeholder*='添加标题']"
            )
            body = @(
                "textarea[placeholder*='正文']",
                "textarea[placeholder*='描述']",
                "[contenteditable='true']",
                ".ql-editor"
            )
            summary = @()
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
