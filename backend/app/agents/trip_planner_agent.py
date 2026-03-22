"""多智能体旅行规划系统"""

import json
from typing import Dict, Any, List
from hello_agents import SimpleAgent
from hello_agents.tools import MCPTool
from ..services.llm_service import get_llm
from ..models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
from ..config import get_settings
from ..prompting import ContextCompressor, InstructionResolver
from ..retrieval import RAGInjector
from ..memory import get_session_memory_service, get_user_profile_service

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。你的任务是根据城市和用户偏好搜索合适的景点。

**重要提示:**
你必须使用工具来搜索景点!不要自己编造景点信息!

**工具调用格式:**
使用maps_text_search工具时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_text_search:keywords=景点关键词,city=城市名]`

**示例:**
用户: "搜索北京的历史文化景点"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=历史文化,city=北京]

用户: "搜索上海的公园"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=公园,city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 参数用逗号分隔
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。你的任务是查询指定城市的天气信息。

**重要提示:**
你必须使用工具来查询天气!不要自己编造天气信息!

**工具调用格式:**
使用maps_weather工具时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_weather:city=城市名]`

**示例:**
用户: "查询北京天气"
你的回复: [TOOL_CALL:amap_maps_weather:city=北京]

用户: "上海的天气怎么样"
你的回复: [TOOL_CALL:amap_maps_weather:city=上海]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。你的任务是根据城市和景点位置推荐合适的酒店。

**重要提示:**
你必须使用工具来搜索酒店!不要自己编造酒店信息!

**工具调用格式:**
使用maps_text_search工具搜索酒店时,必须严格按照以下格式:
`[TOOL_CALL:amap_maps_text_search:keywords=酒店,city=城市名]`

**示例:**
用户: "搜索北京的酒店"
你的回复: [TOOL_CALL:amap_maps_text_search:keywords=酒店,city=北京]

**注意:**
1. 必须使用工具,不要直接回答
2. 格式必须完全正确,包括方括号和冒号
3. 关键词使用"酒店"或"宾馆"
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
"""


class MultiAgentTripPlanner:
    """多智能体旅行规划系统"""

    def __init__(self):
        """初始化多智能体系统"""
        print("🔄 开始初始化多智能体旅行规划系统...")

        try:
            settings = get_settings()
            self.llm = get_llm()
            self.context_compressor = ContextCompressor(
                recent_turns=settings.context_recent_turns,
                summary_trigger_turns=settings.context_summary_trigger_turns,
            )
            self.instruction_resolver = InstructionResolver()
            self.rag_enabled = settings.rag_enabled
            self.rag_injector = RAGInjector(
                knowledge_path=settings.rag_knowledge_path,
                top_k=settings.rag_top_k,
                retrieval_mode=settings.rag_retrieval_mode,
                keyword_weight=settings.rag_keyword_weight,
                vector_weight=settings.rag_vector_weight,
                confidence_weight=settings.rag_confidence_weight,
                vector_backend=settings.rag_vector_backend,
                pgvector_dsn=settings.pgvector_dsn,
                pgvector_table=settings.pgvector_table,
                pgvector_dim=settings.pgvector_dim,
            ) if self.rag_enabled else None
            self.session_memory_enabled = settings.session_memory_enabled
            self.session_memory = get_session_memory_service(
                ttl_minutes=settings.session_memory_ttl_minutes
            ) if self.session_memory_enabled else None
            self.user_profile_enabled = settings.user_profile_enabled
            self.user_profile = get_user_profile_service() if self.user_profile_enabled else None

            # 创建共享的MCP工具(只创建一次)
            print("  - 创建共享MCP工具...")
            self.amap_tool = MCPTool(
                name="amap",
                description="高德地图服务",
                server_command=["uvx", "amap-mcp-server"],
                env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
                auto_expand=True
            )

            # 创建景点搜索Agent
            print("  - 创建景点搜索Agent...")
            self.attraction_agent = SimpleAgent(
                name="景点搜索专家",
                llm=self.llm,
                system_prompt=ATTRACTION_AGENT_PROMPT
            )
            self.attraction_agent.add_tool(self.amap_tool)

            # 创建天气查询Agent
            print("  - 创建天气查询Agent...")
            self.weather_agent = SimpleAgent(
                name="天气查询专家",
                llm=self.llm,
                system_prompt=WEATHER_AGENT_PROMPT
            )
            self.weather_agent.add_tool(self.amap_tool)

            # 创建酒店推荐Agent
            print("  - 创建酒店推荐Agent...")
            self.hotel_agent = SimpleAgent(
                name="酒店推荐专家",
                llm=self.llm,
                system_prompt=HOTEL_AGENT_PROMPT
            )
            self.hotel_agent.add_tool(self.amap_tool)

            # 创建行程规划Agent(不需要工具)
            print("  - 创建行程规划Agent...")
            self.planner_agent = SimpleAgent(
                name="行程规划专家",
                llm=self.llm,
                system_prompt=PLANNER_AGENT_PROMPT
            )

            print(f"✅ 多智能体系统初始化成功")
            print(f"   景点搜索Agent: {len(self.attraction_agent.list_tools())} 个工具")
            print(f"   天气查询Agent: {len(self.weather_agent.list_tools())} 个工具")
            print(f"   酒店推荐Agent: {len(self.hotel_agent.list_tools())} 个工具")
            print(
                f"   上下文压缩: recent_turns={settings.context_recent_turns}, "
                f"summary_trigger_turns={settings.context_summary_trigger_turns}"
            )
            print(
                f"   RAG: enabled={settings.rag_enabled}, "
                f"top_k={settings.rag_top_k}, path={settings.rag_knowledge_path}, "
                f"mode={settings.rag_retrieval_mode}, vector_backend={settings.rag_vector_backend}"
            )
            print(f"   冲突指令消解: enabled={settings.instruction_conflict_guard_enabled}")
            print(
                f"   短期会话记忆: enabled={settings.session_memory_enabled}, "
                f"ttl_minutes={settings.session_memory_ttl_minutes}"
            )
            print(f"   长期用户画像: enabled={settings.user_profile_enabled}")

        except Exception as e:
            print(f"❌ 多智能体系统初始化失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def plan_trip(self, request: TripRequest) -> TripPlan:
        """
        使用多智能体协作生成旅行计划

        Args:
            request: 旅行请求

        Returns:
            旅行计划
        """
        try:
            print(f"\n{'='*60}")
            print(f"🚀 开始多智能体协作规划旅行...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            print(f"{'='*60}\n")

            # 读取并合并长期用户画像
            long_term_profile = self._load_user_profile(request)
            profile_enhanced_request = self._merge_request_with_profile(request, long_term_profile)

            # 读取并合并会话记忆
            session_memory_slots = self._load_session_memory(profile_enhanced_request)
            memory_enhanced_request = self._merge_request_with_session_memory(profile_enhanced_request, session_memory_slots)

            # 步骤1: 景点搜索Agent搜索景点
            print("📍 步骤1: 搜索景点...")
            attraction_query = self._build_attraction_query(memory_enhanced_request)
            attraction_response = self.attraction_agent.run(attraction_query)
            print(f"景点搜索结果: {attraction_response[:200]}...\n")

            # 步骤2: 天气查询Agent查询天气
            print("🌤️  步骤2: 查询天气...")
            weather_query = f"请查询{memory_enhanced_request.city}的天气信息"
            weather_response = self.weather_agent.run(weather_query)
            print(f"天气查询结果: {weather_response[:200]}...\n")

            # 步骤3: 酒店推荐Agent搜索酒店
            print("🏨 步骤3: 搜索酒店...")
            hotel_query = f"请搜索{memory_enhanced_request.city}的{memory_enhanced_request.accommodation}酒店"
            hotel_response = self.hotel_agent.run(hotel_query)
            print(f"酒店搜索结果: {hotel_response[:200]}...\n")

            # 步骤4: 行程规划Agent整合信息生成计划
            print("📋 步骤4: 生成行程计划...")
            compressed_context = self.context_compressor.build_context(memory_enhanced_request.conversation_history)
            print(
                f"上下文压缩完成: 历史轮次={len(memory_enhanced_request.conversation_history)}, "
                f"保留最近轮次={len(compressed_context['recent_turns'])}"
            )
            retrieved_knowledge = []
            rag_block = ""
            if self.rag_enabled and self.rag_injector:
                retrieved_knowledge = self.rag_injector.retrieve(memory_enhanced_request, compressed_context)
                rag_block = self.rag_injector.build_prompt_block(retrieved_knowledge)
            print(f"RAG检索完成: 命中知识条目={len(retrieved_knowledge)}")
            memory_block = self._build_memory_block(session_memory_slots)
            profile_block = self._build_profile_block(long_term_profile)
            planner_query = self._build_planner_query(
                memory_enhanced_request,
                attraction_response,
                weather_response,
                hotel_response,
                compressed_context,
                rag_block,
                memory_block,
                profile_block,
            )
            planner_response = self.planner_agent.run(planner_query)
            print(f"行程规划结果: {planner_response[:300]}...\n")

            # 解析最终计划
            trip_plan = self._parse_response(planner_response, memory_enhanced_request)
            self._update_session_memory(memory_enhanced_request, trip_plan)
            self._update_user_profile(memory_enhanced_request)

            print(f"{'='*60}")
            print(f"✅ 旅行计划生成完成!")
            print(f"{'='*60}\n")

            return trip_plan

        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._create_fallback_plan(request)
    
    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询 - 直接包含工具调用"""
        keywords = []
        if request.preferences:
            # 只取第一个偏好作为关键词
            keywords = request.preferences[0]
        else:
            keywords = "景点"

        # 直接返回工具调用格式
        query = f"请使用amap_maps_text_search工具搜索{request.city}的{keywords}相关景点。\n[TOOL_CALL:amap_maps_text_search:keywords={keywords},city={request.city}]"
        return query

    def _build_planner_query(
        self,
        request: TripRequest,
        attractions: str,
        weather: str,
        hotels: str = "",
        compressed_context: Dict[str, Any] | None = None,
        rag_block: str = "",
        memory_block: str = "",
        profile_block: str = "",
    ) -> str:
        """构建行程规划查询"""
        context_block = ""
        if compressed_context:
            summary = compressed_context.get("summary", {})
            recent_turns = compressed_context.get("recent_turns", [])
            context_block = f"""
**上下文压缩摘要:**
{json.dumps(summary, ensure_ascii=False, indent=2)}

**最近对话原文({len(recent_turns)}轮):**
{json.dumps(recent_turns, ensure_ascii=False, indent=2)}
"""

        instruction_block = self._build_instruction_block(request, rag_block)

        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}
{context_block}
{rag_block}
{memory_block}
{profile_block}
{instruction_block}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query

    def _load_user_profile(self, request: TripRequest) -> Dict[str, Any]:
        if not self.user_profile_enabled or not self.user_profile or not request.user_id:
            return {}
        profile = self.user_profile.load(request.user_id)
        if profile:
            print(f"👤 已加载长期画像: user_id={request.user_id}, plan_count={profile.get('plan_count', 0)}")
        return profile

    def _merge_request_with_profile(self, request: TripRequest, profile: Dict[str, Any]) -> TripRequest:
        if not profile:
            return request
        payload = request.model_dump()
        if not payload.get("preferences"):
            payload["preferences"] = profile.get("top_preferences", [])
        if not payload.get("free_text_input"):
            hints = []
            if profile.get("preferred_transportation"):
                hints.append(f"用户常用交通方式: {profile['preferred_transportation']}")
            if profile.get("preferred_accommodation"):
                hints.append(f"用户常选住宿: {profile['preferred_accommodation']}")
            if hints:
                payload["free_text_input"] = "；".join(hints)
        return TripRequest(**payload)

    def _load_session_memory(self, request: TripRequest) -> Dict[str, Any]:
        if not self.session_memory_enabled or not self.session_memory or not request.session_id:
            return {}
        slots = self.session_memory.load(request.session_id)
        if slots:
            print(f"🧠 已加载会话记忆: session_id={request.session_id}, keys={list(slots.keys())}")
        return slots

    def _merge_request_with_session_memory(self, request: TripRequest, slots: Dict[str, Any]) -> TripRequest:
        if not slots:
            return request
        payload = request.model_dump()
        for key in ["city", "transportation", "accommodation", "travel_days"]:
            if not payload.get(key) and slots.get(key):
                payload[key] = slots[key]
        if not payload.get("preferences") and slots.get("preferences"):
            payload["preferences"] = slots["preferences"]
        if slots.get("conversation_history"):
            history = payload.get("conversation_history", [])
            payload["conversation_history"] = slots["conversation_history"] + history
        return TripRequest(**payload)

    def _build_memory_block(self, slots: Dict[str, Any]) -> str:
        if not slots:
            return ""
        return (
            "\n**短期会话记忆(Session Memory):**\n"
            f"{json.dumps(slots, ensure_ascii=False, indent=2)}\n"
            "请优先沿用会话中已确认的偏好与约束，除非用户本轮明确修改。\n"
        )

    def _build_profile_block(self, profile: Dict[str, Any]) -> str:
        if not profile:
            return ""
        return (
            "\n**长期用户画像(Long-term Profile):**\n"
            f"{json.dumps(profile, ensure_ascii=False, indent=2)}\n"
            "请在不违背用户本轮明确要求的前提下，参考长期偏好做个性化规划。\n"
        )

    def _update_session_memory(self, request: TripRequest, trip_plan: TripPlan) -> None:
        if not self.session_memory_enabled or not self.session_memory or not request.session_id:
            return
        patch = {
            "city": request.city,
            "travel_days": request.travel_days,
            "transportation": request.transportation,
            "accommodation": request.accommodation,
            "preferences": request.preferences,
            "last_start_date": request.start_date,
            "last_end_date": request.end_date,
            "last_overall_suggestions": trip_plan.overall_suggestions,
        }
        if request.conversation_history:
            patch["conversation_history"] = [x.model_dump() for x in request.conversation_history[-8:]]
        updated = self.session_memory.update(request.session_id, patch)
        print(f"🧠 会话记忆已更新: session_id={request.session_id}, keys={list(updated.keys())}")

    def _update_user_profile(self, request: TripRequest) -> None:
        if not self.user_profile_enabled or not self.user_profile or not request.user_id:
            return
        patch = {
            "city": request.city,
            "travel_days": request.travel_days,
            "transportation": request.transportation,
            "accommodation": request.accommodation,
            "preferences": request.preferences,
        }
        profile = self.user_profile.update(request.user_id, patch)
        print(
            f"👤 长期画像已更新: user_id={request.user_id}, "
            f"top_preferences={profile.get('top_preferences', [])}"
        )

    def _build_instruction_block(self, request: TripRequest, rag_block: str) -> str:
        settings = get_settings()
        if not settings.instruction_conflict_guard_enabled:
            return ""

        system_rules = [
            "必须返回可解析的JSON格式",
            "必须包含weather_info且覆盖每一天",
            "每天必须包含早中晚三餐",
            "必须包含预算字段并汇总total",
            "知识不足时不得编造，需明确不确定性",
        ]
        developer_rules = [
            "优先依据工具结果和RAG知识片段生成计划",
            "行程密度建议每天2-3个景点",
        ]
        user_rules = [request.free_text_input] if request.free_text_input else []
        retrieved_rules = [rag_block] if rag_block else []

        resolved = self.instruction_resolver.resolve(
            system_rules=system_rules,
            developer_rules=developer_rules,
            user_rules=user_rules,
            retrieved_rules=retrieved_rules,
        )

        conflicts = resolved.get("conflicts", [])
        if conflicts:
            print("⚠️  检测到冲突指令,已按优先级裁决:")
            for item in conflicts[:5]:
                print(f"   - [{item['layer']}] {item['reason']}: {item['directive'][:80]}")
            if len(conflicts) > 5:
                print(f"   ... 还有 {len(conflicts) - 5} 条冲突")

        effective_rules = resolved.get("effective_rules", [])
        if not effective_rules:
            return ""

        formatted = "\n".join([f"{idx}. {rule}" for idx, rule in enumerate(effective_rules, start=1)])
        return f"\n**冲突消解后的生效指令:**\n{formatted}\n"
    
    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应
        
        Args:
            response: Agent响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        try:
            # 尝试从响应中提取JSON
            # 查找JSON代码块
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                # 直接查找JSON对象
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("响应中未找到JSON数据")
            
            # 解析JSON
            data = json.loads(json_str)
            
            # 转换为TripPlan对象
            trip_plan = TripPlan(**data)
            
            return trip_plan
            
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            print(f"   将使用备用方案生成计划")
            return self._create_fallback_plan(request)
    
    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)"""
        from datetime import datetime, timedelta
        
        # 解析日期
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        
        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
                ]
            )
            days.append(day_plan)
        
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。"
        )


# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
