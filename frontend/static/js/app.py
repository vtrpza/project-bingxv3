"""
Main PyScript Application for BingX Trading Bot Dashboard
Coordinates all frontend functionality and real-time updates
"""

import asyncio
import json
from datetime import datetime, timedelta
try:
    from js import document, console, setInterval, clearInterval, setTimeout, window
    import js
except ImportError:
    # Fallback for testing or other environments
    js = None
    document = None
    console = None
    setInterval = None
    clearInterval = None
    setTimeout = None
    window = None
from pyodide.ffi import create_proxy

# Import our modules
from api_client import api_client
from components import ui_components

def convert_jsproxy_to_dict(data):
    """
    Utility function to convert JsProxy objects to Python dictionaries
    """
    try:
        # If it's already a Python dict, return as-is
        if isinstance(data, dict):
            return data
            
        # If it's a string, try to parse as JSON
        if isinstance(data, str):
            import json
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                console.error("Failed to parse string as JSON")
                return None
        
        # If it has to_py method, use it
        if hasattr(data, 'to_py'):
            console.log("Converting JsProxy using to_py() method")
            return data.to_py()
            
        # If it's a JsProxy object, try JSON.stringify conversion
        if str(type(data)) == "<class 'pyodide.ffi.JsProxy'>":
            console.log("Converting JsProxy using JSON.stringify")
            try:
                import json
                return json.loads(js.JSON.stringify(data))
            except Exception as e:
                console.warn(f"JSON.stringify conversion failed: {e}")
                
                # Manual conversion as last resort
                try:
                    converted_data = {}
                    for key in js.Object.keys(data):
                        value = data[key]
                        # Recursively convert nested objects
                        if str(type(value)) == "<class 'pyodide.ffi.JsProxy'>":
                            value = convert_jsproxy_to_dict(value)
                        converted_data[key] = value
                    console.log("Manual JsProxy conversion successful")
                    return converted_data
                except Exception as manual_err:
                    console.error(f"Manual JsProxy conversion failed: {manual_err}")
                    return None
        
        # If we can't convert, return None
        console.error(f"Unable to convert data type: {type(data)}")
        return None
        
    except Exception as e:
        console.error(f"Error in convert_jsproxy_to_dict: {e}")
        return None


class TradingBotApp:
    def __init__(self):
        self.update_interval = None
        self.auto_refresh_enabled = True
        self.refresh_rate = 10000  # 10 seconds (reduzido para evitar concorrência)
        self.current_tab = "scanner"
        
        # Cache para evitar atualizações desnecessárias
        self.last_validation_data = None
        self.last_validation_timestamp = None
        self.update_in_progress = False
        
        # Client-side operation mode - DISABLED
        self.scanning_active = False  # Force disable client-side mode
        self.client_side_cache = None  # Cache disabled
        self.current_search_term = ""
        self.current_filters = {}
        self.current_sort = {'column': 'symbol', 'direction': 'asc'}
        
        # Initialize after DOM is ready
        self.initialize()
    
    def initialize(self):
        """Initialize the application"""
        console.log("Initializing BingX Trading Bot Dashboard...")
        
        # Connect to WebSocket
        api_client.connect_websocket()
        
        # Set up WebSocket event handlers
        api_client.on_message("realtime_update", create_proxy(self.handle_realtime_update))
        api_client.on_message("pong", create_proxy(self.handle_pong))
        
        # Load initial data
        asyncio.create_task(self.load_initial_data())
        
        # Set up auto-refresh
        self.setup_auto_refresh()
        
        # Set up event listeners
        self.setup_event_listeners()
        
        console.log("Dashboard initialized successfully")
    
    async def load_initial_data(self):
        """Load initial dashboard data with proper progress tracking"""
        loading_overlay = document.getElementById("loading-overlay")
        progress_bar = document.getElementById("progress-bar")
        progress_percentage = document.getElementById("progress-percentage")
        progress_subtitle = document.getElementById("progress-subtitle")
        
        loading_overlay.style.display = "flex"
        
        # Initialize progress tracking
        total_steps = 5
        current_step = 0
        
        def update_progress(step, message):
            nonlocal current_step
            current_step = step
            progress = (current_step / total_steps) * 100
            progress_bar.style.width = f"{progress}%"
            progress_percentage.textContent = f"{progress:.0f}%"
            progress_subtitle.textContent = message
            console.log(f"Loading progress: {progress:.0f}% - {message}")
        
        # Set maximum loading time of 5 seconds (reduced from 15)
        loading_timeout = None
        try:
            if js:
                loading_timeout = js.setTimeout(js.Function.fromString("() => { window.forceHideLoading(); }"), 5000)
        except:
            # Fallback if setTimeout not available
            if console:
                console.warn("setTimeout not available, using manual timeout")
        
        try:
            # Step 1: Dashboard summary (critical)
            update_progress(1, "Carregando resumo do dashboard...")
            try:
                await self.update_dashboard_summary()
                console.log("✅ Dashboard summary loaded")
            except Exception as e:
                console.error(f"❌ Dashboard summary failed: {e}")
            
            # Step 2: Validation table (critical)
            update_progress(2, "Carregando tabela de validação...")
            try:
                await self.update_validation_table()
                console.log("✅ Validation table loaded")
            except Exception as e:
                console.error(f"❌ Validation table failed: {e}")
            
            # Step 3: Scanner data (non-critical)
            update_progress(3, "Carregando dados do scanner...")
            try:
                await self.update_scanner_data()
                console.log("✅ Scanner data loaded")
            except Exception as e:
                console.error(f"⚠️ Scanner data failed: {e}")
            
            # Step 4: Trading data (non-critical)
            update_progress(4, "Carregando dados de trading...")
            try:
                await self.update_trading_data()
                console.log("✅ Trading data loaded")
            except Exception as e:
                console.error(f"⚠️ Trading data failed: {e}")
            
            # Step 5: Positions data (non-critical)
            update_progress(5, "Finalizando carregamento...")
            try:
                await self.update_positions_data()
                console.log("✅ Positions data loaded")
            except Exception as e:
                console.error(f"⚠️ Positions data failed: {e}")
            
            # Complete loading
            update_progress(5, "Dados carregados com sucesso!")
            ui_components.show_notification(
                "Dashboard", 
                "Sistema inicializado com sucesso", 
                "success"
            )
            
        except Exception as e:
            console.error(f"Critical error loading initial data: {str(e)}")
            progress_subtitle.textContent = "Erro ao carregar dados"
            ui_components.show_notification(
                "Erro", 
                "Falha crítica ao carregar dados", 
                "error"
            )
        finally:
            # Clear timeout and hide loading immediately on success
            if loading_timeout and js:
                try:
                    js.clearTimeout(loading_timeout)
                except:
                    pass
            
            # Hide loading overlay immediately on completion
            try:
                loading_overlay.style.display = "none"
                console.log("✅ Loading completed - overlay hidden immediately")
            except:
                # Fallback with minimal delay
                if js:
                    try:
                        js.setTimeout(js.Function.fromString("() => { document.getElementById('loading-overlay').style.display = 'none'; }"), 100)
                    except:
                        pass
    
    def _force_hide_loading(self):
        """Force hide loading overlay after timeout"""
        document.getElementById("loading-overlay").style.display = "none"
        ui_components.show_notification(
            "Timeout", 
            "Carregamento demorou mais que esperado", 
            "warning"
        )
        console.warn("⏰ Loading timeout reached - forcing hide")
    
    async def check_scanning_status(self):
        """Check if scanning is currently active - DISABLED: Always use server-side mode"""
        try:
            # Force disable client-side scanning mode
            old_status = self.scanning_active
            self.scanning_active = False
            
            # Se estava em client-side, limpar cache e voltar ao server-side
            if old_status:
                console.log("⏹️  Client-side scanning disabled - reverting to server-side table operations")
                self.clear_client_side_cache()
                
            return False
        except Exception as e:
            console.log(f"Scanner status check disabled (using server-side mode): {e}")
            self.scanning_active = False
            self.clear_client_side_cache()
            return False

    async def load_full_data_for_client_side(self):
        """Load complete data set for client-side operations during scanning"""
        try:
            console.log("Loading complete dataset for client-side operations...")
            
            # Obter todos os dados sem paginação
            full_data = await api_client.get_validation_table(
                page=1,
                per_page=1000,  # Valor alto para pegar todos
                include_invalid=True
            )
            
            if full_data:
                self.client_side_cache = full_data
                console.log(f"Loaded {len(full_data.get('table_data', []))} records for client-side operations")
                
                # Atualizar UI para mostrar que está em modo client-side
                self.show_client_side_mode_indicator(True)
                ui_components.show_notification(
                    "Modo Scanning", 
                    "Tabela otimizada para scanning ativo - operações locais habilitadas", 
                    "info"
                )
                
        except Exception as e:
            console.error(f"Error loading full data: {e}")

    def clear_client_side_cache(self):
        """Clear client-side cache and revert to server-side operations"""
        self.client_side_cache = None
        self.current_search_term = ""
        self.current_filters = {}
        self.current_sort = {'column': 'symbol', 'direction': 'asc'}
        
        self.show_client_side_mode_indicator(False)
        ui_components.show_notification(
            "Modo Server-side", 
            "Scanning parado - voltou para operações server-side", 
            "info"
        )

    def show_client_side_mode_indicator(self, show):
        """Show/hide the client-side mode indicator - ALWAYS HIDDEN"""
        try:
            indicator = document.getElementById("table-mode-indicator")
            if indicator:
                indicator.style.display = "none"  # Always hidden
        except Exception as e:
            console.error(f"Error updating mode indicator: {e}")

    async def update_dashboard_summary(self):
        """Update dashboard summary statistics with comprehensive real data"""
        try:
            # Check scanning status first
            await self.check_scanning_status()
            
            summary_data = await api_client.get_dashboard_summary()
            if summary_data:
                # Update comprehensive dashboard data
                self.update_comprehensive_dashboard(summary_data)
                ui_components.update_stats_cards(summary_data)
        except Exception as e:
            console.error(f"Error updating dashboard summary: {str(e)}")
    
    def update_comprehensive_dashboard(self, data):
        """Update all dashboard sections with real trading data"""
        try:
            # === P&L TOTAL SECTION ===
            total_pnl_elem = document.getElementById("total-pnl")
            pnl_percentage_elem = document.getElementById("pnl-percentage")
            pnl_detail_elem = document.getElementById("pnl-detail")
            
            if total_pnl_elem:
                total_pnl = data.get("total_pnl", 0)
                pnl_percentage = data.get("pnl_percentage", 0)
                unrealized_pnl = data.get("total_unrealized_pnl", 0)
                
                # Update P&L display
                total_pnl_elem.textContent = f"${total_pnl:.2f}"
                total_pnl_elem.className = f"total-pnl {'profit' if total_pnl > 0 else 'loss' if total_pnl < 0 else 'neutral'}"
                
                if pnl_percentage_elem:
                    pnl_percentage_elem.textContent = f"({pnl_percentage:.2f}%)"
                
                if pnl_detail_elem:
                    daily_pnl = data.get("daily_pnl", 0)
                    pnl_detail_elem.textContent = f"Hoje: ${daily_pnl:.2f} | Não Realizado: ${unrealized_pnl:.2f}"
            
            # === TRADES HOJE SECTION ===
            trades_today_elem = document.getElementById("trades-today")
            win_rate_elem = document.getElementById("win-rate")
            wins_elem = document.getElementById("wins")
            losses_elem = document.getElementById("losses")
            
            if trades_today_elem:
                trades_count = data.get("trades_today", 0)
                win_rate = data.get("win_rate", 0)
                wins = data.get("wins", 0)
                losses = data.get("losses", 0)
                
                trades_today_elem.textContent = str(trades_count)
                
                if win_rate_elem:
                    win_rate_elem.textContent = f"{win_rate:.1f}%"
                
                if wins_elem:
                    wins_elem.textContent = f"{wins} vitórias"
                
                if losses_elem:
                    losses_elem.textContent = f"{losses} derrotas"
            
            # === SCANNER STATUS ===
            monitored_assets_elem = document.getElementById("monitored-assets")
            signals_detected_elem = document.getElementById("signals-detected")
            scanner_status_elem = document.getElementById("scanner-status")
            
            if monitored_assets_elem:
                monitored_assets_elem.textContent = str(data.get("monitored_assets", 0))
            
            if signals_detected_elem:
                signals_detected_elem.textContent = str(data.get("symbols_with_signals", 0))
            
            if scanner_status_elem:
                scanner_active = data.get("scanner_active", False)
                scanner_status_elem.textContent = "ATIVO" if scanner_active else "INATIVO"
                scanner_status_elem.className = f"card-status {'active' if scanner_active else 'inactive'}"
            
            # === POSITIONS SECTION ===
            open_positions_elem = document.getElementById("open-positions")
            total_position_value_elem = document.getElementById("total-position-value")
            margin_used_elem = document.getElementById("margin-used")
            positions_status_elem = document.getElementById("positions-status")
            
            if open_positions_elem:
                open_positions = data.get("open_positions", 0)
                open_positions_elem.textContent = str(open_positions)
                
                if positions_status_elem:
                    positions_status_elem.textContent = f"{open_positions} ATIVAS"
            
            if total_position_value_elem:
                position_value = data.get("total_position_value", 0)
                total_position_value_elem.textContent = f"${position_value:.2f}"
            
            if margin_used_elem:
                margin_used = data.get("margin_used", 0)
                account_balance = data.get("account_balance", 1)
                margin_percent = (margin_used / account_balance * 100) if account_balance > 0 else 0
                margin_used_elem.textContent = f"{margin_percent:.1f}%"
            
            # === ALERTS SECTION ===
            alerts_count_elem = document.getElementById("alerts-count")
            alerts_list_elem = document.getElementById("alerts-list")
            
            if alerts_count_elem:
                alerts_count = data.get("alerts_count", 0)
                alerts_count_elem.textContent = str(alerts_count)
                
                if alerts_list_elem:
                    if alerts_count > 0:
                        alerts_list_elem.innerHTML = f'<div class="alert-item">🔔 {alerts_count} sinais ativos detectados</div>'
                    else:
                        alerts_list_elem.innerHTML = '<div class="no-alerts">Nenhum alerta ativo</div>'
            
            # === ROBOT STATUS ===
            robot_state_elem = document.getElementById("robot-state")
            if robot_state_elem:
                robot_status = data.get("robot_state", "Status desconhecido")
                state_text = robot_state_elem.querySelector(".state-text")
                if state_text:
                    state_text.textContent = robot_status
            
            # === SUMMARY CARDS (multiple locations) ===
            summary_cards = [
                {"id": "total-pnl", "value": f"${data.get('total_pnl', 0):.2f}"},
                {"id": "open-positions", "value": str(data.get("open_positions", 0))},
                {"id": "active-signals-count", "value": str(data.get("symbols_with_signals", 0))},
                {"id": "trades-today", "value": str(data.get("trades_today", 0))}
            ]
            
            for card in summary_cards:
                elem = document.getElementById(card["id"])
                if elem:
                    elem.textContent = card["value"]
            
            console.log(f"✅ Dashboard updated: {data.get('monitored_assets', 0)} assets, {data.get('open_positions', 0)} positions, P&L: ${data.get('total_pnl', 0):.2f}")
            
        except Exception as e:
            console.error(f"Error updating comprehensive dashboard: {e}")
    
    async def update_validation_table(self, page=1):
        """Update asset validation table - ALWAYS use server-side logic"""
        # Evita atualizações simultâneas
        if self.update_in_progress:
            console.log("Validation table update already in progress, skipping...")
            return
            
        try:
            self.update_in_progress = True
            
            # Always use server-side mode (client-side disabled)
            console.log(f"Using server-side table update - page {page}")
            
            # Get validation table data with pagination
            validation_data = await api_client.get_validation_table(
                page=page,
                per_page=25,
                include_invalid=True
            )
            
            if validation_data:
                # Verificar se os dados realmente mudaram
                current_timestamp = validation_data.get("summary", {}).get("last_updated")
                
                if (self.last_validation_data is not None and 
                    self.last_validation_timestamp == current_timestamp and
                    page == 1):  # Only skip if same page and timestamp
                    console.log("Validation data unchanged, skipping UI update")
                    return
                
                # Atualizar cache
                self.last_validation_data = validation_data
                self.last_validation_timestamp = current_timestamp
                
                # Atualizar UI
                ui_components.update_validation_table(validation_data)
                
                # Update summary stats
                summary = validation_data.get("summary", {})
                pagination = validation_data.get("pagination", {})
                self.update_validation_stats(summary)
                
                console.log(f"Validation table updated - Page {pagination.get('current_page', 1)}/{pagination.get('total_pages', 1)}, Total: {summary.get('total_assets', 0)}")
                
        except Exception as e:
            console.error(f"Error updating validation table: {str(e)}")
        finally:
            self.update_in_progress = False

    async def update_table_client_side(self):
        """Update table using client-side cached data"""
        try:
            if not self.client_side_cache:
                console.log("No client-side cache available")
                return
                
            # Aplicar filtros, busca e ordenação no cache
            filtered_data = self.apply_client_side_operations(self.client_side_cache)
            
            # Atualizar UI com dados filtrados
            ui_components.update_validation_table(filtered_data)
            
            console.log(f"Client-side table updated - {len(filtered_data.get('table_data', []))} records displayed")
            
        except Exception as e:
            console.error(f"Error in client-side table update: {e}")

    def apply_client_side_operations(self, data):
        """Apply search, filters, and sorting to cached data"""
        try:
            table_data = data.get("table_data", [])
            
            # 1. Aplicar busca
            if self.current_search_term:
                filtered_data = []
                search_lower = self.current_search_term.lower()
                for item in table_data:
                    symbol = item.get("symbol", "").lower()
                    if search_lower in symbol:
                        filtered_data.append(item)
                table_data = filtered_data
            
            # 2. Aplicar filtros
            if self.current_filters:
                if self.current_filters.get("filter_valid_only"):
                    table_data = [item for item in table_data if item.get("validation_status") == "VALID"]
                
                if self.current_filters.get("priority_only"):
                    table_data = [item for item in table_data if item.get("priority_asset")]
                    
                if self.current_filters.get("trading_enabled_only"):
                    table_data = [item for item in table_data if item.get("trading_enabled")]
                    
                risk_filter = self.current_filters.get("risk_level_filter")
                if risk_filter and risk_filter != "all":
                    table_data = [item for item in table_data if item.get("risk_level") == risk_filter.upper()]
            
            # 3. Aplicar ordenação
            if self.current_sort and self.current_sort.get("column"):
                column = self.current_sort["column"]
                reverse = self.current_sort["direction"] == "desc"
                
                def get_sort_key(item):
                    value = item.get(column)
                    if value is None:
                        return ""
                    # Para colunas numéricas
                    if column in ["validation_score", "current_price", "volume_24h_quote", "spread_percent", "data_quality_score", "age_days"]:
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            return 0
                    # Para texto
                    return str(value).lower()
                
                table_data.sort(key=get_sort_key, reverse=reverse)
            
            # Criar estrutura de retorno simulando paginação
            return {
                "table_data": table_data,
                "summary": data.get("summary", {}),
                "pagination": {
                    "current_page": 1,
                    "total_pages": 1,
                    "total_records": len(table_data),
                    "showing_records": len(table_data)
                }
            }
            
        except Exception as e:
            console.error(f"Error applying client-side operations: {e}")
            return data
    
    async def search_and_update_table(self, search_term="", page=1):
        """Search and update validation table - ALWAYS use server-side logic"""
        try:
            console.log(f"Performing search for: '{search_term}' on page {page}")
            
            # Atualizar termo de busca atual
            self.current_search_term = search_term
            
            # Always use server-side search
            console.log("Using server-side search")
            
            # Get search results from API with pagination
            validation_data = await api_client.get_validation_table(
                page=page,
                per_page=25,
                include_invalid=True,
                search=search_term if search_term else None
            )
            
            if validation_data:
                ui_components.update_validation_table(validation_data)
            
            # Update search indicator
            search_input = document.getElementById("symbol-search")
            if search_input:
                if search_term:
                    search_input.style.backgroundColor = "#e8f4fd"
                    search_input.style.borderColor = "#0969da"
                else:
                    search_input.style.backgroundColor = ""
                    search_input.style.borderColor = ""
                        
        except Exception as e:
            console.error(f"Error during search: {str(e)}")
    
    async def sort_validation_table_server(self, column, direction):
        """Sort validation table with adaptive client/server-side logic"""
        try:
            console.log(f"Sorting: {column} {direction}")
            
            # Atualizar ordenação atual
            self.current_sort = {'column': column, 'direction': direction}
            
            # Se scanning ativo e temos cache, usar client-side
            if self.scanning_active and self.client_side_cache:
                console.log("Using client-side sorting (scanning active)")
                await self.update_table_client_side()
            else:
                # Usar server-side normal
                console.log("Using server-side sorting")
                
                # Get current search term
                search_input = document.getElementById("symbol-search")
                search_term = search_input.value.strip() if search_input else ""
                
                # Get sorted data from API
                validation_data = await api_client.get_validation_table(
                    page=1,  # Reset to first page on sort
                    per_page=25,
                    sort_by=column,
                    sort_direction=direction,
                    include_invalid=True,
                    search=search_term if search_term else None
                )
                
                if validation_data:
                    ui_components.update_validation_table(validation_data)
                
        except Exception as e:
            console.error(f"Error sorting table: {str(e)}")
    
    async def refresh_validation_table_page(self, page):
        """Refresh validation table for specific page"""
        try:
            console.log(f"Refreshing validation table page {page}")
            
            # Get current search and sort
            search_input = document.getElementById("symbol-search")
            search_term = search_input.value.strip() if search_input else ""
            
            current_sort = getattr(ui_components, '_current_sort', {'column': 'symbol', 'direction': 'asc'})
            
            # Get page data from API
            validation_data = await api_client.get_validation_table(
                page=page,
                per_page=25,
                sort_by=current_sort.get('column', 'symbol'),
                sort_direction=current_sort.get('direction', 'asc'),
                include_invalid=True,
                search=search_term if search_term else None
            )
            
            if validation_data:
                ui_components.update_validation_table(validation_data)
                
        except Exception as e:
            console.error(f"Error refreshing page: {str(e)}")
    
    async def apply_validation_table_filters(self, filters):
        """Apply filters to validation table with adaptive client/server-side logic"""
        try:
            console.log(f"Applying filters: {filters}")
            
            # Atualizar filtros atuais
            self.current_filters = filters
            
            # Se scanning ativo e temos cache, usar client-side
            if self.scanning_active and self.client_side_cache:
                console.log("Using client-side filtering (scanning active)")
                await self.update_table_client_side()
            else:
                # Usar server-side normal
                console.log("Using server-side filtering")
                
                # Get current search and sort
                search_input = document.getElementById("symbol-search")
                search_term = search_input.value.strip() if search_input else ""
                
                current_sort = getattr(ui_components, '_current_sort', {'column': 'symbol', 'direction': 'asc'})
                
                # Get filtered data from API
                validation_data = await api_client.get_validation_table(
                    page=1,  # Reset to first page on filter
                    per_page=25,
                    sort_by=current_sort.get('column', 'symbol'),
                    sort_direction=current_sort.get('direction', 'asc'),
                    filter_valid_only=filters.get('filter_valid_only', False),
                    include_invalid=not filters.get('filter_valid_only', False),
                    search=search_term if search_term else None,
                    risk_level_filter=filters.get('risk_level_filter'),
                    priority_only=filters.get('priority_only', False),
                    trading_enabled_only=filters.get('trading_enabled_only', False)
                )
                
                if validation_data:
                    ui_components.update_validation_table(validation_data)
                
        except Exception as e:
            console.error(f"Error applying filters: {str(e)}")
    
    def update_validation_stats(self, summary):
        """Update validation statistics in the UI"""
        try:
            # Update stats cards
            elements = {
                "total-symbols-count": summary.get("total_assets", 0),
                "valid-assets-count": summary.get("valid_assets", 0),
                "assets-with-signals-count": summary.get("assets_with_signals", 0)
            }
            
            for element_id, value in elements.items():
                element = document.getElementById(element_id)
                if element:
                    element.textContent = str(value)
                    
            # Update last update time
            last_update = summary.get("last_updated")
            if last_update:
                update_element = document.getElementById("last-update")
                if update_element:
                    # Parse ISO timestamp and format to UTC-3
                    try:
                        dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        # Convert to UTC-3
                        dt_utc3 = dt - timedelta(hours=3)
                        update_element.textContent = dt_utc3.strftime("%H:%M:%S (UTC-3)")
                    except:
                        update_element.textContent = "Agora"
                        
        except Exception as e:
            console.error(f"Error updating validation stats: {str(e)}")
    
    async def update_scanner_data(self):
        """Update scanner tab data"""
        try:
            # Get latest indicators
            indicators_data = await api_client.get_latest_indicators(50)
            if indicators_data and indicators_data.get("indicators"):
                ui_components.update_scanner_grid(indicators_data["indicators"])
                
        except Exception as e:
            console.error(f"Error updating scanner data: {str(e)}")
    
    async def update_trading_tab_data(self):
        """Update trading tab positions and trades data"""
        try:
            # Get active positions
            positions_data = await api_client.get_positions(active_only=True)
            if positions_data and positions_data.get("positions"):
                ui_components.update_positions_table(positions_data["positions"])
            
            # Get recent trades
            trades_data = await api_client.get_trades(limit=20)
            if trades_data and trades_data.get("trades"):
                ui_components.update_trades_table(trades_data["trades"])
                
        except Exception as e:
            console.error(f"Error updating trading tab data: {str(e)}")
    
    async def update_trading_data(self):
        """Update trading data table with comprehensive real-time information"""
        try:
            # Update trading live data
            trading_data = await api_client.get_trading_live_data(limit=20)
            if trading_data and trading_data.get("success"):
                # Extract trading_data array from response
                assets = trading_data.get("trading_data", [])
                if assets and len(assets) > 0:
                    # Call JavaScript function to update table with proper data mapping
                    try:
                        if hasattr(document.defaultView, 'updateTradingTable'):
                            document.defaultView.updateTradingTable(assets)
                            console.log(f"Trading data table updated with {len(assets)} assets")
                        else:
                            console.warn("updateTradingTable function not available - using fallback")
                            # Fallback to PyScript method
                            self.update_realtime_trading_table(trading_data)
                    except Exception as js_error:
                        console.error(f"Error calling JavaScript updateTradingTable: {js_error}")
                        # Fallback to PyScript method  
                        self.update_realtime_trading_table(trading_data)
                else:
                    self.show_empty_trading_table()
            else:
                console.warn("No trading data received from API")
                # Show empty state in table
                self.show_empty_trading_table()
                # Check if we should show scan required notification
                ui_components.show_notification(
                    "🔍 Scan Inicial", 
                    "Nenhum dado de trading disponível - execute o scan inicial", 
                    "warning"
                )
            
            # Update active signals from signal processor
            await self.update_active_signals()
            
        except Exception as e:
            error_msg = str(e)
            console.error(f"Error updating trading data: {error_msg}")
            self.show_error_trading_table(error_msg)
    
    async def update_active_signals(self):
        """Update active trading signals from signal processor"""
        try:
            # Get active signals from the signal processor
            signals_data = await api_client.get("/signals/active")
            if signals_data and signals_data.get("success"):
                signals = signals_data.get("signals", [])
                self.update_signals_display(signals)
                console.log(f"Active signals updated: {len(signals)} signals")
            else:
                self.show_empty_signals_display()
        except Exception as e:
            console.error(f"Error updating active signals: {e}")
    
    def update_signals_display(self, signals):
        """Update the active signals display section"""
        try:
            signals_container = document.getElementById("active-signals-container")
            if not signals_container:
                console.warn("Active signals container not found")
                return
            
            if not signals or len(signals) == 0:
                self.show_empty_signals_display()
                return
            
            # Build signals HTML
            signals_html = ""
            for signal in signals:
                symbol = signal.get("symbol", "N/A")
                signal_type = signal.get("signal_type", "NEUTRAL")
                strength = signal.get("strength", 0)
                rules = signal.get("rules_triggered", [])
                timestamp = signal.get("timestamp", "")
                
                # Format timestamp
                formatted_time = timestamp.split("T")[1][:8] if "T" in timestamp else timestamp
                
                # Determine signal class
                signal_class = "buy" if signal_type == "BUY" else "sell" if signal_type == "SELL" else "neutral"
                
                # Format strength as percentage
                strength_percent = f"{float(strength) * 100:.1f}%"
                
                # Join rules
                rules_text = ", ".join(rules) if rules else "N/A"
                
                signal_html = f'''
                    <div class="signal-card signal-{signal_class}">
                        <div class="signal-header">
                            <span class="signal-symbol">{symbol}</span>
                            <span class="signal-time">{formatted_time}</span>
                        </div>
                        <div class="signal-content">
                            <div class="signal-type {signal_class}">{signal_type}</div>
                            <div class="signal-strength">Força: {strength_percent}</div>
                            <div class="signal-rules">Regras: {rules_text}</div>
                        </div>
                        <div class="signal-actions">
                            <button onclick="executeSignalTrade('{symbol}', '{signal_type}', {{}})" 
                                    class="signal-execute-btn">
                                📈 Executar Trade
                            </button>
                        </div>
                    </div>
                '''
                signals_html += signal_html
            
            signals_container.innerHTML = signals_html
            console.log(f"✅ Signals display updated with {len(signals)} active signals")
            
        except Exception as e:
            console.error(f"Error updating signals display: {e}")
    
    def show_empty_signals_display(self):
        """Show empty state in signals display"""
        try:
            signals_container = document.getElementById("active-signals-container")
            if signals_container:
                signals_container.innerHTML = '''
                    <div class="no-signals-message">
                        📭 Nenhum sinal ativo no momento<br>
                        <small>Os sinais de trading aparecerão aqui quando detectados</small>
                    </div>
                '''
        except Exception as e:
            console.error(f"Error showing empty signals display: {e}")
    
    def update_realtime_trading_table(self, trading_response):
        """Update the real-time trading data table with comprehensive market data"""
        try:
            if not trading_response.get("success"):
                console.error("Trading data response was not successful")
                return
            
            trading_data = trading_response.get("trading_data", [])
            tbody = document.getElementById("trading-data-tbody")
            
            if not tbody:
                console.error("Trading data table body not found")
                return
            
            if not trading_data:
                self.show_empty_trading_table()
                return
            
            # Build table rows
            rows_html = ""
            for item in trading_data:
                symbol = item.get("symbol", "N/A")
                timestamp = item.get("timestamp", "")
                
                # Format timestamp
                formatted_time = timestamp.split("T")[1][:8] if "T" in timestamp else timestamp
                
                # Spot data
                spot_price = item.get("spot_price", 0)
                spot_mm1 = item.get("spot_mm1", 0)  
                spot_center = item.get("spot_center", 0)
                spot_rsi = item.get("spot_rsi", 0)
                spot_volume = item.get("spot_volume", 0)
                
                # 2H data
                price_2h = item.get("price_2h", 0)
                mm1_2h = item.get("mm1_2h", 0)
                center_2h = item.get("center_2h", 0)
                rsi_2h = item.get("rsi_2h", 0)
                volume_2h = item.get("volume_2h", 0)
                candle_2h = item.get("candle_2h", "🔴")
                signal_2h = item.get("signal_2h", "NEUTRAL")
                
                # 4H data
                price_4h = item.get("price_4h", 0)
                mm1_4h = item.get("mm1_4h", 0)
                center_4h = item.get("center_4h", 0)
                rsi_4h = item.get("rsi_4h", 0)
                volume_4h = item.get("volume_4h", 0)
                candle_4h = item.get("candle_4h", "🔴")
                signal_4h = item.get("signal_4h", "NEUTRAL")
                
                # Overall signal and position
                overall_signal = signal_2h if signal_2h != "NEUTRAL" else signal_4h
                signal_class = "buy" if overall_signal == "BUY" else "sell" if overall_signal == "SELL" else "neutral"
                
                # Position info
                position_info = item.get("position", "Sem posição")
                pnl_info = item.get("pnl", "N/A")
                
                # Format numbers safely
                def format_price(value):
                    try:
                        return f"${float(value):.4f}" if value and value != 0 else "-"
                    except:
                        return "-"
                
                def format_rsi(value):
                    try:
                        return f"{float(value):.1f}" if value and value != 0 else "-"
                    except:
                        return "-"
                
                def format_volume(value):
                    try:
                        vol = float(value)
                        if vol >= 1000000:
                            return f"{vol/1000000:.1f}M"
                        elif vol >= 1000:
                            return f"{vol/1000:.1f}K"
                        else:
                            return f"{vol:.0f}"
                    except:
                        return "-"
                
                row_html = f'''
                    <tr class="trading-row {signal_class}">
                        <td class="symbol-cell"><strong>{symbol}</strong></td>
                        <td class="datetime-cell">{formatted_time}</td>
                        
                        <!-- SPOT columns -->
                        <td class="price-cell">{format_price(spot_price)}</td>
                        <td class="mm1-cell">{format_price(spot_mm1)}</td>
                        <td class="center-cell">{format_price(spot_center)}</td>
                        <td class="rsi-cell">{format_rsi(spot_rsi)}</td>
                        <td class="volume-cell">{format_volume(spot_volume)}</td>
                        
                        <!-- 2H columns -->
                        <td class="candle-cell">{candle_2h}</td>
                        <td class="price-cell">{format_price(price_2h)}</td>
                        <td class="mm1-cell">{format_price(mm1_2h)}</td>
                        <td class="center-cell">{format_price(center_2h)}</td>
                        <td class="rsi-cell">{format_rsi(rsi_2h)}</td>
                        <td class="volume-cell">{format_volume(volume_2h)}</td>
                        
                        <!-- 4H columns -->
                        <td class="candle-cell">{candle_4h}</td>
                        <td class="price-cell">{format_price(price_4h)}</td>
                        <td class="mm1-cell">{format_price(mm1_4h)}</td>
                        <td class="center-cell">{format_price(center_4h)}</td>
                        <td class="rsi-cell">{format_rsi(rsi_4h)}</td>
                        <td class="volume-cell">{format_volume(volume_4h)}</td>
                        
                        <!-- Signal, Position, P&L -->
                        <td class="signal-cell signal-{signal_class}">{overall_signal}</td>
                        <td class="position-cell">{position_info}</td>
                        <td class="pnl-cell">{pnl_info}</td>
                    </tr>
                '''
                rows_html += row_html
            
            # Update table
            tbody.innerHTML = rows_html
            
            # Update last update time
            update_elem = document.getElementById("trading-last-update")
            if update_elem:
                try:
                    current_time = js.Date().toLocaleTimeString()
                    update_elem.textContent = f"Última atualização: {current_time}"
                except:
                    # Fallback without js
                    update_elem.textContent = "Última atualização: agora"
            
            console.log(f"✅ Real-time trading table updated with {len(trading_data)} assets")
            
        except Exception as e:
            console.error(f"Error updating real-time trading table: {e}")
            self.show_error_trading_table(str(e))
    
    def show_empty_trading_table(self):
        """Show empty state in trading table"""
        try:
            tbody = document.getElementById("trading-data-tbody")
            if tbody:
                tbody.innerHTML = '''
                    <tr>
                        <td colspan="22" style="text-align: center; padding: 20px;">
                            <div class="no-data-message">
                                📭 Nenhum dado de trading disponível no momento<br>
                                <small>Execute o scan inicial para começar o monitoramento</small>
                            </div>
                        </td>
                    </tr>
                '''
        except Exception as e:
            console.error(f"Error showing empty trading table: {e}")
    
    def show_error_trading_table(self, error_msg):
        """Show error state in trading table"""
        try:
            tbody = document.getElementById("trading-data-tbody")
            if tbody:
                tbody.innerHTML = f'''
                    <tr>
                        <td colspan="22" style="text-align: center; padding: 20px; color: #f85149;">
                            <div class="error-message">
                                ❌ Erro ao carregar dados: {error_msg}<br>
                                <small>Verifique a conexão e tente novamente</small>
                            </div>
                        </td>
                    </tr>
                '''
        except Exception as e:
            console.error(f"Error showing error in trading table: {e}")
            
            # Check if error indicates scan is required (specific exception from api_client)
            if error_msg.startswith("SCAN_REQUIRED:"):
                ui_components.show_notification(
                    "🔍 Scan Inicial Necessário", 
                    "Execute o scan inicial para descobrir ativos válidos para trading", 
                    "warning"
                )
                console.warn("Trading data requires initial scan - showing user guidance")
            elif ("no_valid_symbols" in error_msg or 
                  "424" in error_msg or 
                  ("500" in error_msg and "trading data error" in error_msg.lower())):
                ui_components.show_notification(
                    "🔍 Scan Inicial Necessário", 
                    "Execute o scan inicial para descobrir ativos válidos", 
                    "warning"
                )
            else:
                ui_components.show_notification(
                    "Erro Trading", 
                    "Falha ao carregar dados de trading", 
                    "error"
                )
    
    async def update_positions_data(self):
        """Update positions and trades tables"""
        try:
            # Update positions table
            positions_data = await api_client.get_positions()
            if positions_data:
                ui_components.update_positions_table(positions_data)
            
            # Update trades history table
            trades_data = await api_client.get_trades_history()
            if trades_data:
                ui_components.update_trades_table(trades_data)
                
        except Exception as e:
            console.error(f"Error updating positions data: {str(e)}")
    
    async def refresh_trading_data(self):
        """Manual refresh of trading data"""
        try:
            await self.update_trading_data()
            await self.update_positions_data()
            await self.update_trades_history()
            
            # Update last refresh timestamp
            try:
                current_time = js.Date().toLocaleTimeString()
            except:
                current_time = "agora"
                
            last_update_element = document.getElementById("trading-last-update")
            if last_update_element:
                last_update_element.textContent = f"Última atualização: {current_time}"
                
            ui_components.show_notification(
                "Trading", 
                "Dados de trading atualizados com sucesso", 
                "success"
            )
        except Exception as e:
            error_msg = str(e)
            console.error(f"Error refreshing trading data: {error_msg}")
            
            # Check if error indicates scan is required
            if error_msg.startswith("SCAN_REQUIRED:"):
                ui_components.show_notification(
                    "🔍 Scan Inicial Necessário", 
                    "Execute o scan inicial antes de atualizar dados de trading", 
                    "warning"
                )
            else:
                ui_components.show_notification(
                    "Erro", 
                    "Falha ao atualizar dados de trading", 
                    "error"
                )
    
    async def update_positions_data(self):
        """Update active positions table with real-time data"""
        try:
            # Get positions data from the enhanced dashboard summary
            summary_data = await api_client.get_dashboard_summary()
            if not summary_data:
                self.show_empty_positions_table()
                return
            
            # Try to get detailed positions from a positions endpoint if available
            try:
                positions_data = await api_client.get("/positions?active_only=true")
                if positions_data and positions_data.get("success"):
                    self.update_positions_table(positions_data.get("positions", []))
                else:
                    # Show empty positions
                    self.show_empty_positions_table()
            except:
                # Fallback to summary data
                self.show_empty_positions_table()
                
        except Exception as e:
            console.error(f"Error updating positions data: {e}")
            self.show_error_positions_table(str(e))
    
    def update_positions_table(self, positions):
        """Update the positions table with real trading positions"""
        try:
            tbody = document.getElementById("positions-tbody")
            if not tbody:
                console.error("Positions table body not found")
                return
            
            if not positions or len(positions) == 0:
                self.show_empty_positions_table()
                return
            
            rows_html = ""
            for position in positions:
                symbol = position.get("symbol", "N/A")
                side = position.get("side", "N/A")
                entry_price = position.get("entry_price", 0)
                current_price = position.get("current_price", 0)
                pnl = position.get("unrealized_pnl", 0)
                pnl_percent = position.get("unrealized_pnl_percent", 0)
                stop_loss = position.get("stop_loss", 0)
                take_profit = position.get("take_profit", 0)
                duration = position.get("duration_hours", 0)
                
                # Determine P&L class
                pnl_class = "profit" if pnl > 0 else "loss" if pnl < 0 else "neutral"
                side_class = "buy" if side == "BUY" else "sell"
                
                # Format stop loss display
                stop_loss_display = f"${float(stop_loss):.4f}" if stop_loss else "-"
                take_profit_display = f"${float(take_profit):.4f}" if take_profit else "Próximo: +3%"
                
                row_html = f'''
                    <tr class="position-row">
                        <td class="symbol-cell"><strong>{symbol}</strong></td>
                        <td class="side-cell {side_class}">{side}</td>
                        <td class="price-cell">${float(entry_price):.4f}</td>
                        <td class="price-cell">${float(current_price):.4f}</td>
                        <td class="pnl-cell {pnl_class}">
                            ${float(pnl):.2f}<br>
                            <small>({float(pnl_percent):.2f}%)</small>
                        </td>
                        <td class="stop-loss-cell">{stop_loss_display}</td>
                        <td class="trailing-cell">
                            {"🟢 Ativo" if pnl > 0 else "⏸️ Inativo"}
                        </td>
                        <td class="tp-cell">{take_profit_display}</td>
                        <td class="duration-cell">{float(duration):.1f}h</td>
                        <td class="status-cell">
                            {"📈 Em alta" if pnl > 0 else "📉 Em baixa" if pnl < 0 else "⚖️ Neutro"}
                        </td>
                        <td class="actions-cell">
                            <button onclick="closePosition('{position.get('trade_id', '')}')" class="close-btn">Fechar</button>
                        </td>
                    </tr>
                '''
                rows_html += row_html
            
            tbody.innerHTML = rows_html
            console.log(f"✅ Positions table updated with {len(positions)} active positions")
            
        except Exception as e:
            console.error(f"Error updating positions table: {e}")
            self.show_error_positions_table(str(e))
    
    def show_empty_positions_table(self):
        """Show empty state in positions table"""
        try:
            tbody = document.getElementById("positions-tbody")
            if tbody:
                tbody.innerHTML = '''
                    <tr>
                        <td colspan="11" style="text-align: center; padding: 20px;">
                            <div class="no-data-message">
                                📭 Nenhuma posição ativa no momento<br>
                                <small>As posições abertas aparecerão aqui automaticamente</small>
                            </div>
                        </td>
                    </tr>
                '''
        except Exception as e:
            console.error(f"Error showing empty positions table: {e}")
    
    def show_error_positions_table(self, error_msg):
        """Show error state in positions table"""
        try:
            tbody = document.getElementById("positions-tbody")
            if tbody:
                tbody.innerHTML = f'''
                    <tr>
                        <td colspan="11" style="text-align: center; padding: 20px; color: #f85149;">
                            <div class="error-message">
                                ❌ Erro ao carregar posições: {error_msg}
                            </div>
                        </td>
                    </tr>
                '''
        except Exception as e:
            console.error(f"Error showing error in positions table: {e}")
    
    async def update_trades_history(self):
        """Update trades history table with recent trading activity"""
        try:
            # Get trades history
            trades_data = await api_client.get("/trades?limit=20")
            if trades_data and trades_data.get("success"):
                self.update_trades_table(trades_data.get("trades", []))
            else:
                self.show_empty_trades_table()
                
        except Exception as e:
            console.error(f"Error updating trades history: {e}")
            self.show_error_trades_table(str(e))
    
    def update_trades_table(self, trades):
        """Update the trades history table"""
        try:
            tbody = document.getElementById("trades-tbody")
            if not tbody:
                console.error("Trades table body not found")
                return
            
            if not trades or len(trades) == 0:
                self.show_empty_trades_table()
                return
            
            rows_html = ""
            for trade in trades:
                entry_time = trade.get("entry_time", "")
                symbol = trade.get("symbol", "N/A")
                side = trade.get("side", "N/A")
                quantity = trade.get("quantity", 0)
                price = trade.get("entry_price", 0)
                status = trade.get("status", "N/A")
                
                # Format timestamp
                formatted_time = ""
                if entry_time:
                    try:
                        # Parse ISO timestamp and format
                        if "T" in entry_time:
                            date_part = entry_time.split("T")[0]
                            time_part = entry_time.split("T")[1][:8]
                            formatted_time = f"{date_part} {time_part}"
                        else:
                            formatted_time = entry_time
                    except:
                        formatted_time = entry_time
                
                side_class = "buy" if side == "BUY" else "sell"
                status_class = "completed" if status == "CLOSED" else "active" if status == "OPEN" else "pending"
                
                row_html = f'''
                    <tr class="trade-row">
                        <td class="datetime-cell">{formatted_time}</td>
                        <td class="symbol-cell"><strong>{symbol}</strong></td>
                        <td class="side-cell {side_class}">{side}</td>
                        <td class="quantity-cell">{float(quantity):.4f}</td>
                        <td class="price-cell">${float(price):.4f}</td>
                        <td class="status-cell {status_class}">{status}</td>
                    </tr>
                '''
                rows_html += row_html
            
            tbody.innerHTML = rows_html
            console.log(f"✅ Trades history updated with {len(trades)} trades")
            
        except Exception as e:
            console.error(f"Error updating trades table: {e}")
            self.show_error_trades_table(str(e))
    
    def show_empty_trades_table(self):
        """Show empty state in trades table"""
        try:
            tbody = document.getElementById("trades-tbody")
            if tbody:
                tbody.innerHTML = '''
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 20px;">
                            <div class="no-data-message">
                                📭 Nenhum histórico de trades disponível<br>
                                <small>Os trades executados aparecerão aqui</small>
                            </div>
                        </td>
                    </tr>
                '''
        except Exception as e:
            console.error(f"Error showing empty trades table: {e}")
    
    def show_error_trades_table(self, error_msg):
        """Show error state in trades table"""
        try:
            tbody = document.getElementById("trades-tbody")
            if tbody:
                tbody.innerHTML = f'''
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 20px; color: #f85149;">
                            <div class="error-message">
                                ❌ Erro ao carregar histórico: {error_msg}
                            </div>
                        </td>
                    </tr>
                '''
        except Exception as e:
            console.error(f"Error showing error in trades table: {e}")
    
    async def execute_auto_trade(self, symbol, signal_type, signal_data):
        """Execute automatic trade when signal is detected"""
        try:
            console.log(f"Executing auto trade: {signal_type} for {symbol}")
            
            trade_result = await api_client.execute_signal_trade(symbol, signal_type, signal_data)
            
            if trade_result and trade_result.get("success"):
                ui_components.show_notification(
                    "Trade Executado", 
                    f"{signal_type} executado para {symbol} em VST mode", 
                    "success"
                )
                
                # Refresh trading data to show new position
                await self.refresh_trading_data()
                
                return True
            else:
                error_msg = trade_result.get("error", "Erro desconhecido") if trade_result else "Resposta inválida"
                ui_components.show_notification(
                    "Erro no Trade", 
                    f"Falha ao executar {signal_type} para {symbol}: {error_msg}", 
                    "error"
                )
                return False
                
        except Exception as e:
            console.error(f"Error executing auto trade: {str(e)}")
            ui_components.show_notification(
                "Erro de Execução", 
                f"Erro ao executar trade para {symbol}: {str(e)}", 
                "error"
            )
            return False
    
    def filter_trading_data_table(self, filters):
        """Filter trading data table"""
        try:
            ui_components.filter_trading_data_table(filters)
            console.log("Trading data filtered successfully")
        except Exception as e:
            console.error(f"Error filtering trading data: {str(e)}")
    
    async def toggle_auto_trading(self, enable):
        """Toggle auto trading mode"""
        try:
            if enable:
                result = await api_client.start_auto_trading()
                if result and result.get("success"):
                    ui_components.show_notification(
                        "Auto Trading", 
                        "Auto Trading iniciado em VST mode", 
                        "success"
                    )
                    return True
            else:
                result = await api_client.stop_auto_trading()
                if result and result.get("success"):
                    ui_components.show_notification(
                        "Auto Trading", 
                        "Auto Trading parado", 
                        "warning"
                    )
                    return True
            
            return False
        except Exception as e:
            console.error(f"Error toggling auto trading: {str(e)}")
            ui_components.show_notification(
                "Erro", 
                f"Erro ao {'iniciar' if enable else 'parar'} auto trading", 
                "error"
            )
            return False
    
    def handle_realtime_update(self, data):
        """
        Handle real-time WebSocket updates with debounce to prevent data flickering.
        """
        console.log("Real-time update received...")
        try:
            # Convert JsProxy data if needed
            if data is not None:
                converted_data = convert_jsproxy_to_dict(data)
                if converted_data is not None:
                    console.log(f"Real-time update data converted: {type(converted_data)}")
                    # Could process the converted data here if needed
                else:
                    console.warn("Failed to convert real-time update data")
            
            # Só atualiza se não há uma atualização em progresso
            if not self.update_in_progress:
                console.log("Triggering debounced data refresh...")
                # Pequeno delay para evitar múltiplas atualizações simultâneas
                setTimeout = document.defaultView.setTimeout
                setTimeout(create_proxy(lambda: asyncio.create_task(self.debounced_update())), 1000)
            else:
                console.log("Update in progress, ignoring WebSocket update")
        except Exception as e:
            console.error(f"Error handling realtime update: {str(e)}")
    
    async def debounced_update(self):
        """Atualização com debounce para evitar conflitos"""
        try:
            await self.update_validation_table()
            await self.update_dashboard_summary()
        except Exception as e:
            console.error(f"Error in debounced update: {str(e)}")
    
    def handle_pong(self, data):
        """Handle WebSocket pong response"""
        # Keep connection alive - pong received
        pass
    
    def handle_scanner_message(self, data):
        """Handle scanner-related WebSocket messages with UI updates"""
        try:
            # Convert JsProxy to Python dict using utility function
            data = convert_jsproxy_to_dict(data)
            
            if data is None:
                console.error("Failed to convert scanner message data to dict")
                return
            
            # Defensive check for data structure after conversion
            if not isinstance(data, dict):
                console.error(f"Expected dict after conversion, got {type(data)}: {data}")
                return
                
            message_type = data.get("type")
            payload = data.get("payload", {})
            
            if not message_type:
                console.error(f"No message type in data: {data}")
                return
                
        except Exception as e:
            console.error(f"Error parsing scanner message data: {e}")
            console.error(f"Data type: {type(data)}, Data: {data}")
            return
        
        if message_type == "scanner_progress":
            processed = payload.get("processed_count", 0)
            total = payload.get("total_assets", 0)
            progress_percent = payload.get("progress_percentage", 0)
            eta = payload.get("estimated_remaining_time_seconds", 0)
            message = payload.get("message", "Processando...")
            
            # Update scan progress UI elements if they exist
            try:
                progress_bar = document.getElementById("progress-bar")
                progress_percentage_elem = document.getElementById("progress-percentage")
                progress_subtitle = document.getElementById("progress-subtitle")
                progress_eta = document.getElementById("progress-eta")
                processed_count_elem = document.getElementById("processed-count")
                total_count_elem = document.getElementById("total-count")
                
                if progress_bar:
                    progress_bar.style.width = f"{progress_percent}%"
                if progress_percentage_elem:
                    progress_percentage_elem.textContent = f"{progress_percent:.1f}%"
                if progress_subtitle:
                    progress_subtitle.textContent = message
                if progress_eta and eta > 0:
                    minutes = int(eta // 60)
                    seconds = int(eta % 60)
                    eta_text = f"{minutes}m {seconds}s restantes" if minutes > 0 else f"{seconds}s restantes"
                    progress_eta.textContent = eta_text
                if processed_count_elem:
                    processed_count_elem.textContent = str(processed)
                if total_count_elem:
                    total_count_elem.textContent = str(total)
                    
                # Show progress details
                progress_details = document.getElementById("progress-details")
                if progress_details:
                    progress_details.style.display = "block"
                    
            except Exception as e:
                console.error(f"Error updating scanner progress UI: {e}")
            
            # Show notification for major progress milestones
            if processed % 100 == 0 or progress_percent >= 100:
                ui_components.show_notification(
                    "Scanner",
                    f"Processando: {processed}/{total} ({progress_percent:.1f}%)",
                    "info",
                    duration=2000
                )
            
        elif message_type == "scanner_completion":
            valid_assets = payload.get("valid_assets_count", 0)
            total_assets = payload.get("total_assets", 0)
            scan_duration = payload.get("scan_duration_seconds", 0)
            
            # Update final progress state
            try:
                progress_bar = document.getElementById("progress-bar")
                progress_percentage_elem = document.getElementById("progress-percentage")
                progress_subtitle = document.getElementById("progress-subtitle")
                valid_count_elem = document.getElementById("valid-count")
                
                if progress_bar:
                    progress_bar.style.width = "100%"
                if progress_percentage_elem:
                    progress_percentage_elem.textContent = "100%"
                if progress_subtitle:
                    progress_subtitle.textContent = "Scan concluído com sucesso!"
                if valid_count_elem:
                    valid_count_elem.textContent = str(valid_assets)
                    
            except Exception as e:
                console.error(f"Error updating scanner completion UI: {e}")
            
            ui_components.show_notification(
                "Scanner Concluído",
                f"Scan finalizado! {valid_assets}/{total_assets} ativos válidos em {scan_duration:.1f}s",
                "success",
                duration=5000
            )
            
            # Hide loading overlay after completion
            try:
                if js:
                    js.setTimeout(js.Function.fromString("() => { document.getElementById('loading-overlay').style.display = 'none'; }"), 2000)
            except:
                pass
                
            # Refresh validation table after completion
            asyncio.create_task(self.update_validation_table())
            
        elif message_type == "scanner_error":
            error_message = payload.get("message", "Erro desconhecido no scanner")
            
            # Update error state in UI
            try:
                progress_subtitle = document.getElementById("progress-subtitle")
                if progress_subtitle:
                    progress_subtitle.textContent = f"Erro: {error_message}"
            except Exception as e:
                console.error(f"Error updating scanner error UI: {e}")
                
            ui_components.show_notification(
                "Erro no Scanner",
                f"Ocorreu um erro durante o scan: {error_message}",
                "error",
                duration=8000
            )
            
            # Hide loading overlay on error
            try:
                if js:
                    js.setTimeout(js.Function.fromString("() => { document.getElementById('loading-overlay').style.display = 'none'; }"), 3000)
            except:
                pass

    def setup_auto_refresh(self):
        """Set up automatic data refresh"""
        # Clear any existing interval first
        if hasattr(self, 'update_interval') and self.update_interval:
            clearInterval(self.update_interval)
            
        def refresh_task():
            if self.auto_refresh_enabled and not getattr(self, 'update_in_progress', False):
                # Add safety check to prevent recursive calls
                try:
                    asyncio.create_task(self.refresh_current_tab())
                except Exception as e:
                    console.error(f"Error in refresh task: {e}")
        
        # Enable auto-refresh for both scanner and trading tabs
        if self.current_tab in ["scanner", "trading"]:
            self.update_interval = setInterval(
                create_proxy(refresh_task), 
                self.refresh_rate
            )
    
    async def refresh_current_tab(self):
        """Refresh data for current active tab with debounce"""
        # Prevent recursive calls with timestamp-based debounce
        try:
            current_time = js.Date.now()
        except NameError:
            # Fallback if js is not available
            import time
            current_time = int(time.time() * 1000)
        
        if hasattr(self, '_last_refresh_time') and (current_time - self._last_refresh_time) < 1000:
            console.log("Refresh called too soon, debouncing...")
            return
        
        # Evita refresh se há atualização em progresso
        if self.update_in_progress:
            console.log("Update in progress, skipping scheduled refresh")
            return
        
        # Set refresh timestamp to prevent recursion
        self._last_refresh_time = current_time
        
        try:
            console.log(f"Refreshing {self.current_tab} tab...")
            
            if self.current_tab == "scanner":
                await self.update_validation_table()
                await self.update_scanner_data()
            elif self.current_tab == "trading":
                # Auto-refresh enabled for trading tab
                console.log("Trading tab - auto-refresh enabled, updating data...")
                await self.update_trading_data()
            
            # Always update summary (but only if validation isn't updating)
            if not self.update_in_progress:
                await self.update_dashboard_summary()
            
        except Exception as e:
            console.error(f"Error refreshing {self.current_tab} tab: {str(e)}")
    
    def setup_event_listeners(self):
        """Set up DOM event listeners"""
        # Auto-refresh checkbox
        auto_refresh_checkbox = document.getElementById("auto-refresh")
        if auto_refresh_checkbox:
            def toggle_auto_refresh(event):
                self.auto_refresh_enabled = event.target.checked
                if self.auto_refresh_enabled:
                    ui_components.show_notification(
                        "Auto-refresh", 
                        "Atualização automática ativada", 
                        "info"
                    )
                else:
                    ui_components.show_notification(
                        "Auto-refresh", 
                        "Atualização automática desativada", 
                        "warning"
                    )
            
            auto_refresh_checkbox.addEventListener(
                "change", 
                create_proxy(toggle_auto_refresh)
            )
        
        # Tab switching
        tab_buttons = document.querySelectorAll(".tab-button")
        for button in tab_buttons:
            def on_tab_click(event):
                # Extract tab name from onclick attribute or data
                tab_name = event.target.textContent.strip()
                previous_tab = self.current_tab
                
                if "Scanner" in tab_name:
                    self.current_tab = "scanner"
                elif "Trading" in tab_name:
                    self.current_tab = "trading"
                elif "Analytics" in tab_name:
                    self.current_tab = "analytics"
                
                # Only refresh if tab actually changed and not in progress
                if self.current_tab != previous_tab and not getattr(self, 'update_in_progress', False):
                    # Don't auto-refresh trading tab
                    if self.current_tab != "trading":
                        try:
                            asyncio.create_task(self.refresh_current_tab())
                        except Exception as e:
                            console.error(f"Error refreshing tab: {e}")
                    else:
                        console.log("Trading tab selected - use manual refresh button")
            
            button.addEventListener("click", create_proxy(on_tab_click))
        
    
    def cleanup(self):
        """Cleanup resources"""
        if self.update_interval:
            clearInterval(self.update_interval)
        
        api_client.disconnect_websocket()


# Global functions for HTML onclick handlers
def refreshData():
    """Global function to refresh data manually"""
    asyncio.create_task(app.load_initial_data())

def closePosition(position_id):
    """Global function to close a position"""
    ui_components.show_notification(
        "Posição", 
        f"Fechamento de posição {position_id} solicitado", 
        "info"
    )
    # TODO: Implement position closing API call

def refreshValidationTable():
    """Global function to refresh validation table"""
    if app.update_in_progress:
        ui_components.show_notification(
            "Tabela", 
            "Atualização já em progresso, aguarde...", 
            "warning"
        )
        return
        
    asyncio.create_task(app.update_validation_table())
    ui_components.show_notification(
        "Tabela", 
        "Atualizando tabela de validação...", 
        "info"
    )

def exportTableData():
    """Global function to export table data"""
    ui_components.export_validation_table()
    ui_components.show_notification(
        "Export", 
        "Dados exportados para CSV", 
        "success"
    )

def sortTable(column):
    """Global function to sort table by column"""
    ui_components.sort_validation_table(column)

def previousPage():
    """Global function for table pagination"""
    ui_components.change_table_page(-1)

def nextPage():
    """Global function for table pagination"""
    ui_components.change_table_page(1)

async def check_revalidation_status():
    """Check the status of revalidation process"""
    status = await api_client.get_revalidation_status()
    if status and status.get("status"):
        status_data = status["status"]
        if status_data.get("running"):
            ui_components.show_notification(
                "Validação", 
                f"Processando... {status_data.get('progress', 0)}/{status_data.get('total', 0)} ativos", 
                "info"
            )
            # Check again in 2 seconds
            setTimeout = document.defaultView.setTimeout
            setTimeout(create_proxy(lambda: asyncio.create_task(check_revalidation_status())), 2000)
        elif status_data.get("completed"):
            ui_components.show_notification(
                "Validação", 
                f"Revalidação concluída! {status_data.get('total', 0)} ativos processados", 
                "success"
            )
            # Refresh the validation table
            asyncio.create_task(app.update_validation_table())
        elif status_data.get("error"):
            ui_components.show_notification(
                "Erro", 
                f"Erro na revalidação: {status_data.get('error')}", 
                "error"
            )

def forceRevalidation():
    """Global function to force asset revalidation with better feedback"""
    async def do_revalidation():
        try:
            ui_components.show_notification(
                "Validação", 
                "Enviando solicitação de revalidação...", 
                "info"
            )
            
            result = await api_client.force_revalidation()
            console.log(f"Revalidation result: {result}")
            
            if result is None:
                ui_components.show_notification(
                    "Erro de Validação",
                    "Falha ao iniciar revalidação: resposta da API nula.",
                    "error"
                )
                return

            if not result.get("error"):
                if result.get("status") == "already_running":
                    ui_components.show_notification(
                        "Validação", 
                        result.get("message", "Processo de revalidação já está em execução."), 
                        "warning"
                    )
                else:
                    ui_components.show_notification(
                        "Validação", 
                        result.get("message", "Revalidação iniciada com sucesso!"), 
                        "success"
                    )
                    # Start checking status
                    await check_revalidation_status()
            else:
                error_detail = result.get("detail", "Erro desconhecido")
                ui_components.show_notification(
                    "Erro de Validação", 
                    f"Falha ao iniciar revalidação: {error_detail}", 
                    "error"
                )

        except Exception as e:
            console.error(f"Error in revalidation: {e}")
            ui_components.show_notification(
                "Erro Crítico", 
                f"Erro inesperado na revalidação: {str(e)}", 
                "error"
            )
    
    asyncio.create_task(do_revalidation())


def filterValidationTable():
    """Global function to filter validation table"""
    ui_components.filter_validation_table()

def searchAssets(event):
    """Handle asset search with debouncing"""
    search_term = event.target.value.strip()
    
    # Clear previous timeout if exists
    from js import clearTimeout, setTimeout
    if hasattr(searchAssets, 'timeout'):
        clearTimeout(searchAssets.timeout)
    
    # Debounce search for 500ms
    def perform_search():
        console.log(f"Searching for: '{search_term}'")
        try:
            # Call the method on the global app instance
            asyncio.create_task(app.search_and_update_table(search_term))
        except NameError:
            console.error("Global app instance not available")
            ui_components.show_notification("Erro", "Sistema não inicializado", "error")
        except Exception as e:
            console.error(f"Search error: {e}")
            ui_components.show_notification("Erro de Pesquisa", f"Erro ao buscar: {e}", "error")
    
    searchAssets.timeout = setTimeout(create_proxy(perform_search), 500)

def clearSearch():
    """Clear search input and refresh table"""
    search_input = document.getElementById("symbol-search")
    if search_input:
        search_input.value = ""
        try:
            asyncio.create_task(app.search_and_update_table("", 1))
        except NameError:
            console.error("Global app instance not available for clearSearch")
            ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def sortValidationTableServer(column, direction):
    """Global function for server-side sorting"""
    try:
        asyncio.create_task(app.sort_validation_table_server(column, direction))
    except NameError:
        console.error("Global app instance not available for sorting")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def refreshValidationTablePage(page):
    """Global function to refresh specific page"""
    try:
        asyncio.create_task(app.refresh_validation_table_page(page))
    except NameError:
        console.error("Global app instance not available for pagination")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def applyValidationTableFilters(filters):
    """Global function to apply filters"""
    try:
        asyncio.create_task(app.apply_validation_table_filters(filters))
    except NameError:
        console.error("Global app instance not available for filters")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

# Trading Tab Global Functions
def updateTradingDataTable(trading_data):
    """Global function to update trading data table"""
    try:
        ui_components.update_trading_data_table(trading_data)
    except Exception as e:
        console.error(f"Error updating trading data table: {e}")
        ui_components.show_notification("Erro", "Falha ao atualizar tabela de trading", "error")

def filterTradingDataTable(filters):
    """Global function to filter trading data table"""
    try:
        app.filter_trading_data_table(filters)
    except NameError:
        console.error("Global app instance not available for trading filters")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def refreshTradingData():
    """Global function to refresh trading data"""
    try:
        asyncio.create_task(app.refresh_trading_data())
    except NameError:
        console.error("Global app instance not available for trading refresh")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

def executeSignalTrade(symbol, signal_type, signal_data):
    """Global function to execute signal trade"""
    try:
        asyncio.create_task(app.execute_auto_trade(symbol, signal_type, signal_data))
    except NameError:
        console.error("Global app instance not available for trade execution")
        ui_components.show_notification("Erro", "Sistema não inicializado", "error")

# Removed toggleAutoTrading function to avoid conflicts with JavaScript version

# Initialize the application first (with singleton protection)
if 'app' not in globals() or app is None:
    app = TradingBotApp()
    console.log("Trading bot app instance created")
else:
    console.log("Trading bot app already exists, reusing instance")

# Make functions globally available
document.refreshData = create_proxy(refreshData)
document.refreshValidationTable = create_proxy(refreshValidationTable)
document.exportTableData = create_proxy(exportTableData)
document.sortTable = create_proxy(sortTable)
document.previousPage = create_proxy(previousPage)

# Bridge function for JavaScript to send trading data to PyScript
def updateTradingDataFromAPI(trading_data):
    """Bridge function to receive data from JavaScript API call"""
    try:
        console.log(f"🌉 Bridge: Received {len(trading_data)} items from JavaScript")
        
        if app and hasattr(app, 'update_trading_table_with_api_data'):
            app.update_trading_table_with_api_data(trading_data)
        else:
            # Direct update if method doesn't exist
            ui_components.update_trading_table(trading_data)
            
        console.log("✅ Trading table updated via bridge")
    except Exception as e:
        console.error(f"❌ Bridge error: {e}")

# Make bridge function available to JavaScript
window.updateTradingDataFromAPI = create_proxy(updateTradingDataFromAPI)
document.nextPage = create_proxy(nextPage)
document.closePosition = create_proxy(closePosition)
# document.forceRevalidation = create_proxy(forceRevalidation)  # Removed - button no longer exists
document.filterValidationTable = create_proxy(filterValidationTable)
document.searchAssets = create_proxy(searchAssets)
document.clearSearch = create_proxy(clearSearch)
document.showNotification = create_proxy(ui_components.show_notification)

# New server-side functions
document.sortValidationTableServer = create_proxy(sortValidationTableServer)
document.refreshValidationTablePage = create_proxy(refreshValidationTablePage)
document.applyValidationTableFilters = create_proxy(applyValidationTableFilters)

# Trading functions
document.updateTradingDataTable = create_proxy(updateTradingDataTable)
document.filterTradingDataTable = create_proxy(filterTradingDataTable)
document.refreshTradingData = create_proxy(refreshTradingData)
document.executeSignalTrade = create_proxy(executeSignalTrade)
# Removed toggleAutoTrading from document proxy to avoid conflicts

# Also make all functions available on window object for JavaScript compatibility
window.showNotification = create_proxy(ui_components.show_notification)
# window.forceRevalidation = create_proxy(forceRevalidation)  # Removed - button no longer exists
window.refreshValidationTable = create_proxy(refreshValidationTable)
window.exportTableData = create_proxy(exportTableData)
window.sortTable = create_proxy(sortTable)
window.previousPage = create_proxy(previousPage)
window.nextPage = create_proxy(nextPage)
window.clearSearch = create_proxy(clearSearch)
window.searchAssets = create_proxy(searchAssets)

# Trading functions on window
window.updateTradingDataTable = create_proxy(updateTradingDataTable)
window.filterTradingDataTable = create_proxy(filterTradingDataTable)
window.refreshTradingData = create_proxy(refreshTradingData)
window.executeSignalTrade = create_proxy(executeSignalTrade)
window.handleScannerMessage = create_proxy(app.handle_scanner_message)
# Removed toggleAutoTrading from window proxy to avoid conflicts

# Global function to handle scanner WebSocket messages from JavaScript
def handleScannerWebSocketMessage(data):
    """Global function to handle scanner messages from JavaScript WebSocket"""
    try:
        # Debug logging to understand the data structure
        console.log(f"Handling scanner WebSocket message: {type(data)}")
        console.log(f"Data content: {data}")
        
        # Convert data using utility function
        converted_data = convert_jsproxy_to_dict(data)
        
        if converted_data is None:
            console.error(f"Failed to convert scanner WebSocket message data: {type(data)}")
            return
        
        # Final validation
        if not isinstance(converted_data, dict):
            console.error(f"Data is not a dict after conversion: {type(converted_data)}")
            return
            
        app.handle_scanner_message(converted_data)
    except Exception as e:
        console.error(f"Error handling scanner WebSocket message: {e}")
        console.error(f"Error type: {type(e)}")
        console.error(f"Data type: {type(data)}, Data: {data}")

window.handleScannerWebSocketMessage = create_proxy(handleScannerWebSocketMessage)

console.log("BingX Trading Bot Dashboard loaded successfully!")