function Invoke-ZhihuPublish {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    $spec = [pscustomobject]@{
        Key = "zhihu"
        Url = "https://zhuanlan.zhihu.com/write"
        CoverRatio = "16:9"
        EntryHints = @("写文章", "标题", "发布", "草稿", "创作声明")
        ManualBeforeDraft = ""
        PreClickTexts = @()
        ImportMarkdown = $true
        ImportClickTexts = @("导入", "导入文章", "Markdown", "本地文件")
        SkipBodyFillAfterImport = $true
        CoverClickTexts = @("添加文章封面", "添加封面")
        SaveDraftTexts = @("保存草稿", "存草稿")
        SaveOptional = $true
        PublishTexts = @("发布", "发表")
        Selectors = [pscustomobject]@{
            title = @(
                "textarea[placeholder*='标题']",
                "input[placeholder*='标题']",
                "[contenteditable='true'][data-placeholder*='标题']",
                "[contenteditable='true'][placeholder*='标题']"
            )
            body = @(
                ".DraftEditor-root [contenteditable='true']",
                ".ProseMirror",
                ".ql-editor",
                "article [contenteditable='true']",
                "[contenteditable='true']"
            )
            summary = @()
            topics = @(
                "input[placeholder*='话题']",
                "input[placeholder*='添加话题']",
                "input[placeholder*='搜索话题']"
            )
            tags = @()
            hashtags = @()
        }
    }

    Invoke-GenericPlatform $Context $spec $Pack
}
