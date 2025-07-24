"""
Main PyScript Application for BingX Trading Bot Dashboard
Coordinates all frontend functionality and real-time updates
"""

import asyncio
import json
from datetime import datetime
from js import document, console, setInterval, clearInterval, setTimeout
from pyodide.ffi import create_proxy

# Import our modules
from api_client import api_client
from components import ui_components


class TradingBotApp:
    def __init__(self):
        self.update_interval = None
        self.auto_refresh_enabled = True
        self.refresh_rate = 5000  # 5 seconds
        self.current_tab = "scanner"
        
        # Initialize after DOM is ready
        self.initialize()
    
    def initialize(self):
        """Initialize the application"""
        console.log("Initializing BingX Trading Bot Dashboard...")
        
        # Connect to WebSocket
        api_client.connect_websocket()
        
        # Set up WebSocket event handlers
        api_client.on_message("realtime_update", self.handle_realtime_update)
        api_client.on_message("pong", self.handle_pong)
        
        # Load initial data
        asyncio.create_task(self.load_initial_data())
        
        # Set up auto-refresh
        self.setup_auto_refresh()
        
        # Set up event listeners
        self.setup_event_listeners()
        
        console.log("Dashboard initialized successfully")
    
    async def load_initial_data(self):
        """Load initial dashboard data"""
        try:
            document.getElementById("loading-overlay").style.display = "flex"
            
            # Load dashboard summary
            await self.update_dashboard_summary()
            
            # Load validation table
            await self.update_validation_table()
            
            # Load scanner data
            await self.update_scanner_data()
            
            # Load trading data
            await self.update_trading_data()
            
            ui_components.show_notification(
                "Dashboard", 
                "Dados carregados com sucesso", 
                "success"
            )
            
        except Exception as e:
            console.error(f"Error loading initial data: {str(e)}")
            ui_components.show_notification(
                "Erro", 
                "Falha ao carregar dados iniciais", 
                "error"
            )
        finally:
            document.getElementById("loading-overlay").style.display = "none"
    
    async def update_dashboard_summary(self):
        """Update dashboard summary statistics"""
        try:
            summary_data = await api_client.get_dashboard_summary()
            if summary_data:
                ui_components.update_stats_cards(summary_data)
        except Exception as e:
            console.error(f"Error updating dashboard summary: {str(e)}")
    
    async def update_validation_table(self):
        """Update asset validation table"""
        try:
            # Get validation table data
            validation_data = await api_client.get_validation_table()
            if validation_data:
                ui_components.update_validation_table(validation_data)
                # Update summary stats
                summary = validation_data.get("summary", {})
                self.update_validation_stats(summary)
        except Exception as e:
            console.error(f"Error updating validation table: {str(e)}")
    
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
                    # Parse ISO timestamp and format
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                        update_element.textContent = dt.strftime("%H:%M:%S")
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
    
    async def update_trading_data(self):
        """Update trading tab data"""
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
            console.error(f"Error updating trading data: {str(e)}")
    
    def handle_realtime_update(self, data):
        """Handle real-time WebSocket updates"""
        try:
            update_data = data.get("data", {})
            
            # Update indicators in scanner
            indicators = update_data.get("indicators", [])
            if indicators:
                ui_components.update_scanner_grid(indicators)
            
            # Update active signals count
            active_signals = update_data.get("active_signals", 0)
            element = document.getElementById("active-signals-count")
            if element:
                element.textContent = str(active_signals)
            
            # Update positions if available
            positions = update_data.get("active_positions", [])
            if positions:
                # Update P&L in real-time
                total_pnl = sum(
                    float(pos.get("unrealized_pnl", 0)) 
                    for pos in positions
                )
                pnl_element = document.getElementById("total-pnl")
                if pnl_element:
                    pnl_element.textContent = ui_components.format_currency(total_pnl)
                    pnl_element.className = f"pnl-value {ui_components.get_pnl_class(total_pnl)}"
            
            # Update timestamp
            timestamp_element = document.getElementById("last-update")
            if timestamp_element:
                timestamp_element.textContent = datetime.now().strftime("%H:%M:%S")
                
        except Exception as e:
            console.error(f"Error handling realtime update: {str(e)}")
    
    def handle_pong(self, data):
        """Handle WebSocket pong response"""
        # Keep connection alive - pong received
        pass
    
    def setup_auto_refresh(self):
        """Set up automatic data refresh"""
        def refresh_task():
            if self.auto_refresh_enabled:
                asyncio.create_task(self.refresh_current_tab())
        
        # Create interval for auto refresh
        self.update_interval = setInterval(
            create_proxy(refresh_task), 
            self.refresh_rate
        )
    
    async def refresh_current_tab(self):
        """Refresh data for current active tab"""
        try:
            if self.current_tab == "scanner":
                await self.update_validation_table()
                await self.update_scanner_data()
            elif self.current_tab == "trading":
                await self.update_trading_data()
            
            # Always update summary
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
                if "Scanner" in tab_name:
                    self.current_tab = "scanner"
                elif "Trading" in tab_name:
                    self.current_tab = "trading"
                elif "Analytics" in tab_name:
                    self.current_tab = "analytics"
                
                # Refresh data for new tab
                asyncio.create_task(self.refresh_current_tab())
            
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

def forceRevalidation():
    """Global function to force asset revalidation"""
    ui_components.show_notification(
        "Validação", 
        "Revalidação de ativos solicitada", 
        "info"
    )
    # TODO: Implement asset revalidation API call

def filterValidationTable():
    """Global function to filter validation table"""
    ui_components.filter_validation_table()

# Make functions globally available
document.refreshData = refreshData
document.refreshValidationTable = refreshValidationTable
document.exportTableData = exportTableData
document.sortTable = sortTable
document.previousPage = previousPage
document.nextPage = nextPage
document.closePosition = closePosition
document.forceRevalidation = forceRevalidation
document.filterValidationTable = filterValidationTable

# Initialize the application
app = TradingBotApp()

console.log("BingX Trading Bot Dashboard loaded successfully!")