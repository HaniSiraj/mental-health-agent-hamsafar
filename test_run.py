import asyncio, logging
logging.disable(logging.CRITICAL)
from cognitive import run_cognitive_pipeline
async def main():
    s = {'turns': [], 'consent': {'memory': True}}
    reply, trace, sess = await run_cognitive_pipeline('test1', 'I am having anxiety', s)
    print('RESULT_TIER:', trace['safety'].get('tier'), 'AGENTS:', trace['routing'].get('agents'))
    print('RESULT_REPLY:', reply[:300].replace(chr(10), ' '))
asyncio.run(main())
