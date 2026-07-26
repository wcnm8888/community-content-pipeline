function Invoke-BilibiliPublish {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Pack
    )

    $spec = [pscustomobject]@{
        Key = "bilibili"
        Url = "https://member.bilibili.com/platform/upload/text/new-edit?aid=364875"
        CoverRatio = "16:9"
        EntryHints = @("专栏", "标题", "发布", "草稿", "自定义封面", "AI", "创作声明", "话题")
        ManualBeforeDraft = "请确认当前是 B站专栏/图文编辑页，能看到标题、正文、自定义封面、创作声明和话题区域后按 Enter。"
        PreClickTexts = @()
        ImportMarkdown = $true
        ImportClickTexts = @("导入文档", "导入文章", "导入")
        SkipBodyFillAfterImport = $true
        CoverClickTexts = @("自定义封面", "上传封面")
        SaveDraftTexts = @("保存草稿", "存草稿")
        SaveOptional = $false
        PublishTexts = @("发布", "立即发布")
        Selectors = [pscustomobject]@{
            title = @(
                "input[placeholder*='标题']",
                "textarea[placeholder*='标题']",
                "[contenteditable='true'][data-placeholder*='标题']"
            )
            body = @(
                ".ProseMirror",
                ".ql-editor",
                ".DraftEditor-root [contenteditable='true']",
                "textarea[placeholder*='正文']",
                "[contenteditable='true']"
            )
            summary = @(
                "textarea[placeholder*='简介']",
                "textarea[placeholder*='摘要']",
                "textarea[placeholder*='描述']"
            )
            topics = @(
                "input[placeholder*='话题']",
                "input[placeholder*='搜索话题']",
                "input[placeholder*='添加话题']"
            )
            tags = @()
            hashtags = @()
        }
    }

    Invoke-GenericPlatform $Context $spec $Pack
}
