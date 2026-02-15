# OpenClaw Plugins

Drop custom skill files here. Any Python file with a class inheriting from `Skill` will be auto-discovered.

Example:

```python
from openclaw.skills.base import Skill, SkillContext
from openclaw.messages.models import InboundMessage, OutboundMessage
from openclaw.types import Intent

class VibrationSkill(Skill):
    def intents(self):
        return [Intent.DIAGNOSE]

    def name(self):
        return "vibration_analysis"

    async def handle(self, message, context):
        # Your custom logic here
        ...
```
